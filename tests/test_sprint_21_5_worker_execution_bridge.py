from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from models.agent_role import AgentRole
from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.devjob_registry_service import DevJobRegistryService
from services.launch_providers.base import LaunchContext, LaunchOutcome, LaunchProvider
from services.launch_providers.local_command import ClaudeCodeCliLaunchProvider
from services.worker_admission_service import WorkerAdmissionService
from services.worker_execution_bridge_service import WorkerExecutionBridgeService

WORKER = "claude-code-worker-1"
GOV_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR


def _seed_work_context(tmp_path: Path) -> str:
    """Persist a minimal governed Work Context so bridge-target DevJobs are
    execution-ready (Work Context is required at the execution boundary)."""
    work_context_id = f"WORKCTX-{uuid4().hex[:12].upper()}"
    pkg_dir = tmp_path / ".ageix" / "architecture" / "work_context" / work_context_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id, "project_id": "Ageix",
            "work_summary": "Bridge test work context",
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )
    return work_context_id


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

class _AvailableProvider(LaunchProvider):
    provider_key = "test_available"
    worker_type = "claude_code"

    def is_available(self) -> bool:
        return True

    def launch(self, context: LaunchContext) -> LaunchOutcome:
        return LaunchOutcome(launched=True, session_ref={"provider": self.provider_key, "session": "SESSION-XYZ"},
                             detail="launched in test")


class _FailingProvider(LaunchProvider):
    provider_key = "test_failing"
    worker_type = "claude_code"

    def is_available(self) -> bool:
        return True

    def launch(self, context: LaunchContext) -> LaunchOutcome:
        return LaunchOutcome(launched=False, error="launch_provider_spawn_failed", detail="boom")


def _job(tmp_path: Path, *, status: str = "assigned", assigned_to: str | None = WORKER) -> str:
    kwargs = dict(title="Bridge target", objective="Do it", created_by="greg")
    if status == "assigned":
        job = DevJobRegistryService(tmp_path).create_job(
            status="assigned", assigned_to=assigned_to,
            acceptance_criteria=["do it"], allowed_paths=["src/"], prohibited_paths=["secrets/"],
            work_context_id=_seed_work_context(tmp_path), **kwargs,
        )
    else:
        job = DevJobRegistryService(tmp_path).create_job(**kwargs)  # draft, unassigned
    return job.job_id


def _bridge(tmp_path: Path) -> WorkerExecutionBridgeService:
    return WorkerExecutionBridgeService(tmp_path)


def _engage(tmp_path: Path, job_id: str, *, providers, **kw):
    return _bridge(tmp_path).engage_worker(
        devjob_id=job_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE, providers=providers, **kw,
    )


# ---------------------------------------------------------------------------
# 1. No provider -> durable queued launch request; DevJob -> in_progress
# ---------------------------------------------------------------------------

def test_no_provider_creates_queued_request(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    record = _engage(tmp_path, job_id, providers=[])

    assert record["state"] == "worker_queued"
    assert record["launch_provider"] is None
    assert record["devjob_status_after"] == "in_progress"
    assert record["admission_ticket_id"]
    assert record["launch_artifact_id"]
    # Durable: the queued request is persisted and retrievable.
    fetched = _bridge(tmp_path).get_execution(record["execution_id"])
    assert fetched["state"] == "worker_queued"
    assert DevJobRegistryService(tmp_path).get_job(job_id).status == "in_progress"


# ---------------------------------------------------------------------------
# 2. Configured provider launches automatically
# ---------------------------------------------------------------------------

def test_available_provider_launches_worker(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    record = _engage(tmp_path, job_id, providers=[_AvailableProvider()])

    assert record["state"] == "worker_launched"
    assert record["launch_provider"] == "test_available"
    assert record["worker_session_ref"]["session"] == "SESSION-XYZ"
    assert record["devjob_status_after"] == "in_progress"


def test_local_command_provider_launches_real_process(tmp_path: Path) -> None:
    # A configured (opt-in) launch command spawns a real process and returns a pid.
    job_id = _job(tmp_path)
    provider = ClaudeCodeCliLaunchProvider(tmp_path, command="true")
    record = _engage(tmp_path, job_id, providers=[provider])
    assert record["state"] == "worker_launched"
    assert record["launch_provider"] == "claude_code_cli"
    assert isinstance(record["worker_session_ref"].get("pid"), int)


# ---------------------------------------------------------------------------
# 3. Provider available but launch fails -> worker_launch_failed, no transition
# ---------------------------------------------------------------------------

def test_provider_failure_does_not_transition_devjob(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    record = _engage(tmp_path, job_id, providers=[_FailingProvider()])

    assert record["state"] == "worker_launch_failed"
    assert record["devjob_status_after"] == "assigned"
    # DevJob remains launchable / not advanced on failure.
    assert DevJobRegistryService(tmp_path).get_job(job_id).status == "assigned"


# ---------------------------------------------------------------------------
# 4. DevJob transitions only after launch or queue; state on lifecycle
# ---------------------------------------------------------------------------

def test_launch_state_visible_on_devjob_lifecycle(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    record = _engage(tmp_path, job_id, providers=[_AvailableProvider()])

    registry = DevJobRegistryService(tmp_path)
    events = registry.list_events(job_id)
    assert any(e["event_type"] == "worker_launched" for e in events)
    launched = [e for e in events if e["event_type"] == "worker_launched"][0]
    assert launched["metadata"]["execution_id"] == record["execution_id"]
    # The transition is recorded in lifecycle_history with the bridge note.
    history = registry.get_job(job_id).lifecycle_history
    assert any(h["to_status"] == "in_progress" and "worker_execution_bridge" in str(h.get("note")) for h in history)


# ---------------------------------------------------------------------------
# 5. Traceability preserved across the governed chain
# ---------------------------------------------------------------------------

def test_traceability_references_full_chain(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    record = _engage(
        tmp_path, job_id, providers=[_AvailableProvider()],
        directive_turn_id="TURN-ABC123", delegation_id="CHAIRDLG-XYZ", conversation_id="CONV-1",
    )
    trace = record["traceability"]
    assert record["directive_turn_id"] == "TURN-ABC123"
    assert record["delegation_id"] == "CHAIRDLG-XYZ"
    assert trace["admission_ticket_id"] == record["admission_ticket_id"]
    assert trace["launch_artifact_id"] == record["launch_artifact_id"]
    assert trace["governed_artifact_id"]  # the launcher artifact registered a governed artifact
    assert trace["authoritative_store"] == "ageix"
    assert record["worker_session_ref"]["session"] == "SESSION-XYZ"


def test_consumed_delegation_reference_is_recorded_not_rejected(tmp_path: Path) -> None:
    # The bridge is authorized by governance, not by the delegation (which
    # authorized the upstream directive and may already be consumed). A consumed
    # delegation id is accepted as a traceability reference, not re-validated.
    job_id = _job(tmp_path)
    record = _engage(tmp_path, job_id, providers=[_AvailableProvider()], delegation_id="CHAIRDLG-CONSUMED")
    assert record["state"] == "worker_launched"
    assert record["delegation_id"] == "CHAIRDLG-CONSUMED"


# ---------------------------------------------------------------------------
# 6. Clean failures for invalid inputs
# ---------------------------------------------------------------------------

def test_missing_devjob_fails_cleanly(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="worker_execution_devjob_not_found"):
        _engage(tmp_path, "DEVJOB-DOESNOTEXIST1", providers=[])


def test_unassigned_devjob_fails_cleanly(tmp_path: Path) -> None:
    job_id = _job(tmp_path, status="draft")
    with pytest.raises(ValueError, match="worker_execution_devjob_unassigned"):
        _engage(tmp_path, job_id, providers=[])


def test_worker_mismatch_fails_cleanly(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    with pytest.raises(ValueError, match="worker_execution_worker_mismatch"):
        _engage(tmp_path, job_id, providers=[], worker_id="someone-else")


def test_non_launchable_devjob_fails_cleanly(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    _engage(tmp_path, job_id, providers=[])  # -> in_progress
    with pytest.raises(ValueError, match="worker_execution_devjob_not_launchable"):
        _engage(tmp_path, job_id, providers=[])


def test_unauthorized_actor_denied(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    with pytest.raises(ValueError, match="worker_execution_requires_governance"):
        _bridge(tmp_path).engage_worker(
            devjob_id=job_id, actor_id="lex", actor_role=AgentRole.LEX, providers=[],
        )


# ---------------------------------------------------------------------------
# Reuse of admission ticket / launch artifact (no duplication)
# ---------------------------------------------------------------------------

def test_existing_admission_ticket_is_reused(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    admission = WorkerAdmissionService(tmp_path)
    profile = admission.create_profile(name="cc", worker_type="claude_code", created_by="greg")
    ticket = admission.create_ticket(
        target_type="DEVJOB", target_id=job_id, worker_profile_id=profile.profile_id,
        actor_id="greg", actor_role=CHAIR_ROLE,
    )
    record = _engage(tmp_path, job_id, providers=[], worker_profile_id=profile.profile_id)
    # No new ticket minted — the existing issued ticket is reused.
    assert record["admission_ticket_id"] == ticket.ticket_id
    assert admission.list_tickets(target_id=job_id)["total_count"] == 1


# ---------------------------------------------------------------------------
# Governed capability path (worker.launcher.execute)
# ---------------------------------------------------------------------------

def test_capability_execute_queues_without_provider(tmp_path: Path, monkeypatch) -> None:
    # Ensure no ambient launch command makes a provider available.
    monkeypatch.delenv("AGEIX_CLAUDE_CODE_LAUNCH_CMD", raising=False)
    job_id = _job(tmp_path)
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="worker.launcher.execute", session_id="s", agent_id="greg",
        arguments={"actor_id": "greg", "agent_role": "ageix.chair", "devjob_id": job_id, "project_id": "Ageix"},
    ))
    assert response.success is True, response.error
    assert response.result["state"] in ("worker_queued", "worker_launched")
    assert response.result["devjob_status_after"] == "in_progress"


def test_capability_execute_unauthorized_denied(tmp_path: Path) -> None:
    job_id = _job(tmp_path)
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="worker.launcher.execute", session_id="s", agent_id="lex",
        arguments={"actor_id": "lex", "agent_role": "lex", "devjob_id": job_id},
    ))
    assert response.success is False
    assert response.error == "worker_execution_requires_governance"
