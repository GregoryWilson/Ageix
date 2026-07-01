from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from models.agent_role import AgentRole
from models.worker_launch_artifact import LAUNCHER_DENIED_ACTIONS
from services.artifact_registry_service import ArtifactRegistryService
from services.capabilities.worker_launcher_capabilities import register_capabilities
from services.devjob_registry_service import DevJobRegistryService
from services.worker_admission_service import WorkerAdmissionService
from services.worker_launcher_service import GOVERNANCE_LINEAGE, WorkerLauncherService

GOV_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
WORKER_ID = "claude.code-worker-1"
WORKER_ROLE = AgentRole.CLAUDE_CODE
ADAPTER = "claude_code_browser"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _seed_work_context(tmp_path: Path, work_context_id: str | None = None) -> str:
    """Persist a minimal governed Work Context so DevJobs created for launcher
    tests are execution-ready (the Work Context is required at the DevWorker
    execution boundary)."""
    work_context_id = work_context_id or f"WORKCTX-{uuid4().hex[:12].upper()}"
    pkg_dir = tmp_path / ".ageix" / "architecture" / "work_context" / work_context_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id,
            "project_id": "Ageix",
            "work_summary": "Launcher test work context",
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )
    return work_context_id


def _assigned_devjob(tmp_path: Path, *, worker_id: str = WORKER_ID) -> str:
    work_context_id = _seed_work_context(tmp_path)
    job = DevJobRegistryService(tmp_path).create_job(
        title="Launch target",
        objective="Do the thing.",
        acceptance_criteria=["complete the launch target"],
        allowed_paths=["src/"],
        prohibited_paths=["secrets/"],
        work_context_id=work_context_id,
        created_by="greg",
        status="assigned",
        assigned_to=worker_id,
    )
    return job.job_id


def _profile(admission: WorkerAdmissionService, *, worker_type: str = "claude_code", project_id: str = "Ageix") -> str:
    return admission.create_profile(
        name="Claude Code Web Worker",
        worker_type=worker_type,
        permission_mode="constrained_auto",
        project_id=project_id,
        created_by=GOV_ACTOR,
        launch_adapter_hint="claude_code_web",
    ).profile_id


def _ticket(admission: WorkerAdmissionService, tmp_path: Path, *, worker_id: str = WORKER_ID, worker_type: str = "claude_code", project_id: str = "Ageix"):
    job_id = _assigned_devjob(tmp_path, worker_id=worker_id)
    profile_id = _profile(admission, worker_type=worker_type, project_id=project_id)
    ticket = admission.create_ticket(
        target_type="DEVJOB",
        target_id=job_id,
        worker_profile_id=profile_id,
        project_id=project_id,
        actor_id=GOV_ACTOR,
        actor_role=CHAIR_ROLE,
    )
    return ticket, profile_id, job_id


def _setup(tmp_path: Path):
    admission = WorkerAdmissionService(tmp_path)
    launcher = WorkerLauncherService(tmp_path)
    ticket, profile_id, job_id = _ticket(admission, tmp_path)
    return admission, launcher, ticket, profile_id, job_id


# ---------------------------------------------------------------------------
# Happy path: Admission Ticket -> Launch Profile -> Launch Artifact
# ---------------------------------------------------------------------------

def test_create_launch_artifact_happy_path(tmp_path: Path) -> None:
    admission, launcher, ticket, profile_id, job_id = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id,
        adapter=ADAPTER,
        actor_id=GOV_ACTOR,
        actor_role=CHAIR_ROLE,
    )
    assert artifact["launch_artifact_id"].startswith("WLAUNCH-")
    assert artifact["project_id"] == "Ageix"
    assert artifact["admission_ticket_id"] == ticket.ticket_id
    assert artifact["worker_profile_id"] == profile_id
    assert artifact["adapter"] == ADAPTER
    assert artifact["target_type"] == "DEVJOB"
    assert artifact["target_id"] == job_id
    assert artifact["permission_mode"] == "constrained_auto"
    assert artifact["handoff_instructions"], "handoff instructions must be present"
    assert artifact["governed_artifact_id"], "must register a governed artifact"


def test_launch_artifact_does_not_imply_execution(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    assert artifact["non_authoritative"] is True
    assert artifact["execution_performed"] is False
    assert artifact["launch_reference"]["authoritative"] is False


def test_launch_artifact_surfaces_denied_actions(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    assert artifact["denied_actions"] == LAUNCHER_DENIED_ACTIONS
    for denied in ("direct_worker_execution", "validation_worker_sequencing",
                   "patch_application", "chair_approval_bypass", "devjob_completion"):
        assert denied in artifact["denied_actions"]


def test_launch_artifact_preserves_authority_scope(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    scope = artifact["authority_scope"]
    assert scope["chair_authority_preserved"] is True
    assert scope["human_execution_boundary"] == "Greg"
    assert scope["manual_execution"] is True
    assert scope["execute_available"] is False


def test_launch_artifact_carries_traceability(tmp_path: Path) -> None:
    _, launcher, ticket, profile_id, job_id = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    trace = artifact["traceability"]
    assert trace["implementation_proposal_id"] == GOVERNANCE_LINEAGE["implementation_proposal_id"]
    assert trace["architecture_proposal_id"] == GOVERNANCE_LINEAGE["architecture_proposal_id"]
    assert trace["source_architecture_revision"] == GOVERNANCE_LINEAGE["source_architecture_revision"]
    assert trace["admission_ticket_id"] == ticket.ticket_id
    assert trace["worker_profile_id"] == profile_id
    assert trace["target"]["id"] == job_id
    assert trace["authoritative_store"] == "ageix"


# ---------------------------------------------------------------------------
# Governed artifact mechanism reuse
# ---------------------------------------------------------------------------

def test_launch_artifact_registered_in_governed_artifact_registry(tmp_path: Path) -> None:
    _, launcher, ticket, _, job_id = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    registry = ArtifactRegistryService(tmp_path)
    governed = registry.get_artifact(artifact["governed_artifact_id"])
    assert governed["artifact_type"] == "worker_launch_handoff"
    assert governed["source_id"] == artifact["launch_artifact_id"]
    ref_ids = {r["reference_id"] for r in governed["references"]}
    assert ticket.ticket_id in ref_ids
    assert job_id in ref_ids


def test_get_and_list_launch_artifacts(tmp_path: Path) -> None:
    _, launcher, ticket, _, job_id = _setup(tmp_path)
    created = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    fetched = launcher.get_launch_artifact(created["launch_artifact_id"])
    assert fetched["launch_artifact_id"] == created["launch_artifact_id"]

    listed = launcher.list_launch_artifacts(target_id=job_id)
    assert listed["total_count"] == 1
    assert listed["launch_artifacts"][0]["launch_artifact_id"] == created["launch_artifact_id"]


# ---------------------------------------------------------------------------
# Authority boundaries
# ---------------------------------------------------------------------------

def test_unauthorized_actor_cannot_create_launch_artifact(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    with pytest.raises(ValueError, match="worker_launcher_requires_governance"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            actor_id=WORKER_ID, actor_role=WORKER_ROLE,
        )


def test_greg_can_create_launch_artifact(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id="greg", actor_role=AgentRole.UNKNOWN,
    )
    assert artifact["launch_artifact_id"].startswith("WLAUNCH-")


# ---------------------------------------------------------------------------
# Denials
# ---------------------------------------------------------------------------

def test_unknown_adapter_denied(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    with pytest.raises(ValueError, match="worker_launcher_adapter_not_supported"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter="cursor_desktop",
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_missing_ticket_denied(tmp_path: Path) -> None:
    WorkerAdmissionService(tmp_path)
    launcher = WorkerLauncherService(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_ticket_not_found"):
        launcher.create_launch_artifact(
            admission_ticket_id="WADMIT-DOESNOTEXIST1", adapter=ADAPTER,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_redeemed_ticket_denied(tmp_path: Path) -> None:
    admission, launcher, ticket, _, _ = _setup(tmp_path)
    admission.redeem_ticket(ticket_id=ticket.ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)
    with pytest.raises(ValueError, match="worker_launcher_ticket_already_redeemed"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_expired_ticket_denied(tmp_path: Path) -> None:
    admission, launcher, ticket, _, _ = _setup(tmp_path)
    stale = admission.get_ticket(ticket.ticket_id)
    stale.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    admission._save_ticket(stale, append_to_index=False)
    with pytest.raises(ValueError, match="worker_launcher_ticket_expired"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_profile_adapter_mismatch_denied(tmp_path: Path) -> None:
    admission = WorkerAdmissionService(tmp_path)
    launcher = WorkerLauncherService(tmp_path)
    # Profile declares a non-claude_code worker_type, incompatible with the
    # claude_code_browser adapter.
    ticket, _, _ = _ticket(admission, tmp_path, worker_type="local_worker")
    with pytest.raises(ValueError, match="worker_launcher_profile_adapter_mismatch"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_profile_ticket_mismatch_denied(tmp_path: Path) -> None:
    admission, launcher, ticket, _, _ = _setup(tmp_path)
    other_profile = _profile(admission)  # a different profile id
    with pytest.raises(ValueError, match="worker_launcher_profile_ticket_mismatch"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            worker_profile_id=other_profile,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_project_mismatch_denied(tmp_path: Path) -> None:
    admission, launcher, ticket, _, _ = _setup(tmp_path)
    with pytest.raises(ValueError, match="worker_launcher_project_mismatch"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            project_id="SomeOtherProject",
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_missing_target_devjob_denied(tmp_path: Path) -> None:
    admission, launcher, ticket, _, job_id = _setup(tmp_path)
    DevJobRegistryService(tmp_path).delete_job(job_id)
    with pytest.raises(ValueError, match="worker_launcher_target_devjob_not_found"):
        launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


# ---------------------------------------------------------------------------
# Governance preservation: launcher does not touch DevJob / admission state
# ---------------------------------------------------------------------------

def test_launch_artifact_does_not_mutate_devjob_or_ticket(tmp_path: Path) -> None:
    admission, launcher, ticket, _, job_id = _setup(tmp_path)
    devjobs = DevJobRegistryService(tmp_path)
    job_before = devjobs.get_job(job_id)

    launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )

    job_after = devjobs.get_job(job_id)
    ticket_after = admission.get_ticket(ticket.ticket_id)
    # DevJob is untouched and the ticket is NOT redeemed by launch handoff.
    assert job_before.status == job_after.status == "assigned"
    assert len(job_before.lifecycle_history) == len(job_after.lifecycle_history)
    assert ticket_after.status == "issued"
    assert ticket_after.redeemed_at is None


def test_explicit_project_id_ageix_preserved(tmp_path: Path) -> None:
    _, launcher, ticket, _, _ = _setup(tmp_path)
    artifact = launcher.create_launch_artifact(
        admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
        project_id="Ageix",
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    assert artifact["project_id"] == "Ageix"
    assert artifact["traceability"]["authoritative_store"] == "ageix"


# ---------------------------------------------------------------------------
# Adapter unit behavior
# ---------------------------------------------------------------------------

def test_claude_code_browser_adapter_handoff_is_non_authoritative() -> None:
    from models.worker_admission_ticket import WorkerAdmissionTicket
    from models.worker_launch_profile import WorkerLaunchProfile
    from models.worker_launch_request import WorkerLaunchRequest
    from services.launcher_adapters import ClaudeCodeBrowserLauncherAdapter

    ticket = WorkerAdmissionTicket(
        target_id="DEVJOB-ABC123DEF456", worker_profile_id="WLPROFILE-1", worker_id=WORKER_ID,
    )
    profile = WorkerLaunchProfile(name="X", worker_type="claude_code")
    request = WorkerLaunchRequest(admission_ticket_id=ticket.ticket_id, adapter="claude_code_browser")

    handoff = ClaudeCodeBrowserLauncherAdapter().build_handoff(ticket=ticket, profile=profile, request=request)
    assert handoff.launch_reference["authoritative"] is False
    assert handoff.launch_reference["handoff_mode"] == "manual"
    assert any("redeem" in step.lower() for step in handoff.handoff_instructions)
    assert any(ticket.ticket_id in step for step in handoff.handoff_instructions)


# ---------------------------------------------------------------------------
# Capability plugin (handlers invoked directly)
# ---------------------------------------------------------------------------

def _handlers(tmp_path: Path) -> dict[str, object]:
    return {definition.capability_id: handler for definition, handler in register_capabilities(tmp_path)}


def test_capability_plugin_registers_expected_capabilities(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    for capability_id in (
        "worker.launcher.artifact.create",
        "worker.launcher.artifact.get",
        "worker.launcher.artifact.list",
    ):
        assert capability_id in handlers
        assert callable(handlers[capability_id])


def test_capability_unauthorized_create_returns_error(tmp_path: Path) -> None:
    _, _, ticket, _, _ = _setup(tmp_path)
    handlers = _handlers(tmp_path)
    denied = handlers["worker.launcher.artifact.create"]({
        "admission_ticket_id": ticket.ticket_id, "adapter": ADAPTER,
        "actor_id": WORKER_ID, "agent_role": "claude.code",
    })
    assert denied["success"] is False
    assert denied["error"] == "worker_launcher_requires_governance"


def test_capability_create_and_get(tmp_path: Path) -> None:
    _, _, ticket, _, _ = _setup(tmp_path)
    handlers = _handlers(tmp_path)
    created = handlers["worker.launcher.artifact.create"]({
        "admission_ticket_id": ticket.ticket_id, "adapter": ADAPTER,
        "actor_id": "greg", "agent_role": "ageix.chair",
    })
    assert created["success"] is True
    launch_id = created["result"]["launch_artifact_id"]
    fetched = handlers["worker.launcher.artifact.get"]({"launch_artifact_id": launch_id})
    assert fetched["success"] is True
    assert fetched["result"]["launch_artifact_id"] == launch_id
