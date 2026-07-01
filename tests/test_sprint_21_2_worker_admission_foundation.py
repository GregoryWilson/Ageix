from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from models.agent_role import AgentRole
from models.permission_mode import PermissionMode
from models.worker_admission_ticket import WorkerAdmissionTicket
from services.capabilities.worker_admission_capabilities import register_capabilities
from services.devjob_registry_service import DevJobRegistryService
from services.worker_admission_service import WorkerAdmissionService

WORKER_ID = "claude.code-worker-1"
GOV_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
WORKER_ROLE = AgentRole.CLAUDE_CODE


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _seed_work_context(tmp_path: Path, work_context_id: str | None = None) -> str:
    """Persist a minimal governed Work Context so admission-target DevJobs are
    execution-ready (the Work Context is required at the DevWorker execution
    boundary, not at creation)."""
    work_context_id = work_context_id or f"WORKCTX-{uuid4().hex[:12].upper()}"
    pkg_dir = tmp_path / ".ageix" / "architecture" / "work_context" / work_context_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id,
            "project_id": "Ageix",
            "work_summary": "Admission test work context",
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )
    return work_context_id


def _assigned_devjob(tmp_path: Path, *, worker_id: str = WORKER_ID) -> str:
    work_context_id = _seed_work_context(tmp_path)
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Admission target",
        objective="Do the thing.",
        acceptance_criteria=["complete the admission target"],
        allowed_paths=["src/"],
        prohibited_paths=["secrets/"],
        work_context_id=work_context_id,
        created_by="greg",
        status="assigned",
        assigned_to=worker_id,
    )
    return job.job_id


def _profile(svc: WorkerAdmissionService, *, mode: str = "supervised") -> str:
    profile = svc.create_profile(
        name="Claude Code Worker",
        worker_type="claude_code",
        permission_mode=mode,
        created_by=GOV_ACTOR,
        launch_adapter_hint="claude_code_web",
    )
    return profile.profile_id


def _ticket(tmp_path: Path, *, worker_id: str = WORKER_ID, mode: str | None = None) -> tuple[WorkerAdmissionService, str, str]:
    svc = WorkerAdmissionService(tmp_path)
    job_id = _assigned_devjob(tmp_path, worker_id=worker_id)
    profile_id = _profile(svc)
    ticket = svc.create_ticket(
        target_type="DEVJOB",
        target_id=job_id,
        worker_profile_id=profile_id,
        permission_mode=mode,
        actor_id=GOV_ACTOR,
        actor_role=CHAIR_ROLE,
    )
    return svc, ticket.ticket_id, job_id


def _expire(svc: WorkerAdmissionService, ticket_id: str) -> None:
    ticket = svc.get_ticket(ticket_id)
    ticket.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    svc._save_ticket(ticket, append_to_index=False)


# ---------------------------------------------------------------------------
# Permission mode model
# ---------------------------------------------------------------------------

def test_permission_mode_valid_values() -> None:
    assert {m.value for m in PermissionMode} == {"supervised", "constrained_auto", "sandbox_auto"}
    assert PermissionMode.is_valid("constrained_auto")
    assert not PermissionMode.is_valid("yolo")


def test_permission_mode_parse_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="worker_admission_invalid_permission_mode"):
        PermissionMode.parse("root_access")


# ---------------------------------------------------------------------------
# Launch profile creation / listing
# ---------------------------------------------------------------------------

def test_create_and_list_launch_profile(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    profile = svc.create_profile(
        name="Local Worker",
        worker_type="local_worker",
        permission_mode="constrained_auto",
        created_by=GOV_ACTOR,
    )
    assert profile.profile_id.startswith("WLPROFILE-")
    assert profile.permission_mode is PermissionMode.CONSTRAINED_AUTO
    assert (tmp_path / ".ageix" / "worker_admission" / "profiles" / f"{profile.profile_id}.json").exists()

    listed = svc.list_profiles()
    assert listed["total_count"] == 1
    assert listed["profiles"][0]["profile_id"] == profile.profile_id


def test_create_profile_rejects_invalid_permission_mode(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_invalid_permission_mode"):
        svc.create_profile(name="X", worker_type="claude_code", permission_mode="godmode", created_by=GOV_ACTOR)


def test_create_profile_requires_fields(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_profile_name_required"):
        svc.create_profile(name="", worker_type="claude_code", created_by=GOV_ACTOR)
    with pytest.raises(ValueError, match="worker_admission_profile_worker_type_required"):
        svc.create_profile(name="X", worker_type="", created_by=GOV_ACTOR)


# ---------------------------------------------------------------------------
# Ticket creation for DevJob target
# ---------------------------------------------------------------------------

def test_create_ticket_for_devjob_target(tmp_path: Path) -> None:
    svc, ticket_id, job_id = _ticket(tmp_path)
    ticket = svc.get_ticket(ticket_id)
    assert ticket.ticket_id.startswith("WADMIT-")
    assert ticket.target_type == "DEVJOB"
    assert ticket.target_id == job_id
    assert ticket.worker_id == WORKER_ID
    assert ticket.status == "issued"
    assert ticket.single_use is True
    assert ticket.required_next_capability == "devjob.get"


def test_create_ticket_defaults_30_minute_expiry(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    ticket = svc.get_ticket(ticket_id)
    created = datetime.fromisoformat(ticket.created_at)
    expires = datetime.fromisoformat(ticket.expires_at)
    delta = expires - created
    assert timedelta(minutes=29) <= delta <= timedelta(minutes=31)


def test_create_ticket_inherits_profile_permission_mode(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    job_id = _assigned_devjob(tmp_path)
    profile_id = _profile(svc, mode="sandbox_auto")
    ticket = svc.create_ticket(
        target_type="DEVJOB", target_id=job_id, worker_profile_id=profile_id,
        actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
    )
    assert ticket.permission_mode is PermissionMode.SANDBOX_AUTO


def test_create_ticket_unassigned_devjob_is_ambiguous(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(title="Draft", objective="x", created_by="greg")  # draft, unassigned
    profile_id = _profile(svc)
    with pytest.raises(ValueError, match="worker_admission_target_devjob_unassigned"):
        svc.create_ticket(
            target_type="DEVJOB", target_id=job.job_id, worker_profile_id=profile_id,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


# ---------------------------------------------------------------------------
# Ticket expiration
# ---------------------------------------------------------------------------

def test_expired_ticket_redemption_is_denied(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    _expire(svc, ticket_id)
    with pytest.raises(ValueError, match="worker_admission_ticket_expired"):
        svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)


# ---------------------------------------------------------------------------
# Single-use redemption
# ---------------------------------------------------------------------------

def test_successful_redemption_returns_admission_context(tmp_path: Path) -> None:
    svc, ticket_id, job_id = _ticket(tmp_path)
    admission = svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)
    assert admission["admission_ticket_id"] == ticket_id
    assert admission["target_type"] == "DEVJOB"
    assert admission["target_id"] == job_id
    assert admission["permission_mode"] == "supervised"
    assert admission["required_next_capability"] == "devjob.get"
    assert admission["status"] == "redeemed"


def test_single_use_second_redemption_denied(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)
    with pytest.raises(ValueError, match="worker_admission_ticket_already_redeemed"):
        svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)


# ---------------------------------------------------------------------------
# Minimal redemption response / no DevJob payload
# ---------------------------------------------------------------------------

def test_redemption_response_is_minimal_and_excludes_devjob(tmp_path: Path) -> None:
    svc, ticket_id, job_id = _ticket(tmp_path)
    admission = svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)

    expected_keys = {
        "admission_ticket_id", "project_id", "target_type", "target_id",
        "worker_profile_id", "permission_mode", "required_next_capability",
        "status", "expires_at", "redeemed_at", "authoritative_store",
    }
    assert set(admission.keys()) == expected_keys

    # No DevJob payload fields leak into the admission context.
    for forbidden in ("objective", "instructions", "acceptance_criteria", "allowed_paths", "lifecycle_history", "title"):
        assert forbidden not in admission
    assert admission["authoritative_store"] == "ageix"


# ---------------------------------------------------------------------------
# Stale ticket revival / duplication
# ---------------------------------------------------------------------------

def test_revive_redeemed_ticket_creates_fresh_traceable_ticket(tmp_path: Path) -> None:
    svc, ticket_id, job_id = _ticket(tmp_path)
    svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)

    revived = svc.revive_ticket(ticket_id=ticket_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE)
    assert revived.ticket_id != ticket_id
    assert revived.revived_from_ticket_id == ticket_id
    assert revived.status == "issued"
    assert revived.target_id == job_id
    assert revived.worker_id == WORKER_ID
    # Revived ticket is independently redeemable.
    admission = svc.redeem_ticket(ticket_id=revived.ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)
    assert admission["status"] == "redeemed"


def test_revive_expired_ticket_allowed(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    _expire(svc, ticket_id)
    revived = svc.revive_ticket(ticket_id=ticket_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE)
    assert revived.revived_from_ticket_id == ticket_id
    assert not revived.is_expired()


def test_revive_fresh_ticket_denied(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_ticket_not_stale"):
        svc.revive_ticket(ticket_id=ticket_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE)


# ---------------------------------------------------------------------------
# Unsupported target denial
# ---------------------------------------------------------------------------

def test_unsupported_conv_target_denied(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    profile_id = _profile(svc)
    with pytest.raises(ValueError, match="worker_admission_target_unsupported"):
        svc.create_ticket(
            target_type="CONV", target_id="CONV-ABCDEF123456", worker_profile_id=profile_id,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_unsupported_interaction_target_denied(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    profile_id = _profile(svc)
    with pytest.raises(ValueError, match="worker_admission_target_unsupported"):
        svc.create_ticket(
            target_type="INTERACTION", target_id="INTERACTION-ABCDEF12", worker_profile_id=profile_id,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_missing_devjob_target_denied(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    profile_id = _profile(svc)
    with pytest.raises(ValueError, match="worker_admission_target_devjob_not_found"):
        svc.create_ticket(
            target_type="DEVJOB", target_id="DEVJOB-DOESNOTEXIST1", worker_profile_id=profile_id,
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


def test_missing_launch_profile_denied(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    job_id = _assigned_devjob(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_launch_profile_not_found"):
        svc.create_ticket(
            target_type="DEVJOB", target_id=job_id, worker_profile_id="WLPROFILE-NOPE00000001",
            actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )


# ---------------------------------------------------------------------------
# Authorization: creation
# ---------------------------------------------------------------------------

def test_unauthorized_ticket_creation_denied(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    job_id = _assigned_devjob(tmp_path)
    profile_id = _profile(svc)
    # A worker role is NOT authorized to mint admission tickets.
    with pytest.raises(ValueError, match="worker_admission_ticket_create_requires_governance"):
        svc.create_ticket(
            target_type="DEVJOB", target_id=job_id, worker_profile_id=profile_id,
            actor_id=WORKER_ID, actor_role=WORKER_ROLE,
        )


def test_greg_can_create_ticket(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    job_id = _assigned_devjob(tmp_path)
    profile_id = _profile(svc)
    ticket = svc.create_ticket(
        target_type="DEVJOB", target_id=job_id, worker_profile_id=profile_id,
        actor_id="greg", actor_role=AgentRole.UNKNOWN,
    )
    assert ticket.status == "issued"


# ---------------------------------------------------------------------------
# Authorization: redemption
# ---------------------------------------------------------------------------

def test_unauthorized_worker_redemption_denied(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_redeem_worker_not_authorized"):
        svc.redeem_ticket(ticket_id=ticket_id, worker_id="claude.code-imposter", actor_role=WORKER_ROLE)


def test_redemption_denied_when_devjob_reassigned(tmp_path: Path) -> None:
    svc, ticket_id, job_id = _ticket(tmp_path)
    # Simulate the DevJob being reassigned away from the bound worker: redemption
    # must not bypass current DevJob assignment.
    registry = DevJobRegistryService(tmp_path)
    job = registry.get_job(job_id)
    job.assigned_to = "claude.code-someone-else"
    registry._save_job(job)
    with pytest.raises(ValueError, match="worker_admission_redeem_worker_not_authorized"):
        svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)


def test_unauthorized_revive_denied(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    _expire(svc, ticket_id)
    with pytest.raises(ValueError, match="worker_admission_revive_requires_governance"):
        svc.revive_ticket(ticket_id=ticket_id, actor_id=WORKER_ID, actor_role=WORKER_ROLE)


# ---------------------------------------------------------------------------
# Governance boundary preservation
# ---------------------------------------------------------------------------

def test_redemption_does_not_mutate_devjob(tmp_path: Path) -> None:
    svc, ticket_id, job_id = _ticket(tmp_path)
    registry = DevJobRegistryService(tmp_path)
    before = registry.get_job(job_id)
    svc.redeem_ticket(ticket_id=ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)
    after = registry.get_job(job_id)
    # The ticket grants participation, never authority: DevJob state is untouched.
    assert before.status == after.status == "assigned"
    assert before.assigned_to == after.assigned_to
    assert len(before.lifecycle_history) == len(after.lifecycle_history)


def test_ticket_is_non_authoritative_and_carries_no_devjob(tmp_path: Path) -> None:
    svc, ticket_id, _ = _ticket(tmp_path)
    ticket = svc.get_ticket(ticket_id)
    payload = ticket.to_metadata()
    # Ticket references the target but stores no DevJob content.
    for forbidden in ("objective", "instructions", "acceptance_criteria", "allowed_paths"):
        assert forbidden not in payload


def test_unknown_ticket_denied_clearly(tmp_path: Path) -> None:
    svc = WorkerAdmissionService(tmp_path)
    with pytest.raises(ValueError, match="worker_admission_ticket_not_found"):
        svc.get_ticket("WADMIT-DOESNOTEXIST1")


# ---------------------------------------------------------------------------
# Capability plugin (handlers invoked directly, no full discovery)
# ---------------------------------------------------------------------------

def _handlers(tmp_path: Path) -> dict[str, object]:
    return {definition.capability_id: handler for definition, handler in register_capabilities(tmp_path)}


def test_capability_plugin_registers_expected_capabilities(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    for capability_id in (
        "worker.admission.profile.create",
        "worker.admission.profile.list",
        "worker.admission.ticket.create",
        "worker.admission.ticket.get",
        "worker.admission.ticket.redeem",
        "worker.admission.ticket.revive",
    ):
        assert capability_id in handlers
        assert callable(handlers[capability_id])


def test_capability_unauthorized_ticket_create_returns_error(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    job_id = _assigned_devjob(tmp_path)
    profile = handlers["worker.admission.profile.create"]({
        "name": "Claude Code", "worker_type": "claude_code",
        "created_by": "greg", "actor_id": "greg", "agent_role": "ageix.chair",
    })
    profile_id = profile["result"]["profile_id"]
    # Worker role attempting to create a ticket → denied.
    denied = handlers["worker.admission.ticket.create"]({
        "target_type": "DEVJOB", "target_id": job_id, "worker_profile_id": profile_id,
        "actor_id": WORKER_ID, "agent_role": "claude.code",
    })
    assert denied["success"] is False
    assert denied["error"] == "worker_admission_ticket_create_requires_governance"


def test_capability_redeem_returns_minimal_context(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    job_id = _assigned_devjob(tmp_path)
    profile = handlers["worker.admission.profile.create"]({
        "name": "Claude Code", "worker_type": "claude_code",
        "created_by": "greg", "actor_id": "greg", "agent_role": "ageix.chair",
    })
    profile_id = profile["result"]["profile_id"]
    created = handlers["worker.admission.ticket.create"]({
        "target_type": "DEVJOB", "target_id": job_id, "worker_profile_id": profile_id,
        "actor_id": "greg", "agent_role": "ageix.chair",
    })
    assert created["success"] is True
    ticket_id = created["result"]["ticket_id"]

    redeemed = handlers["worker.admission.ticket.redeem"]({
        "ticket_id": ticket_id, "worker_id": WORKER_ID, "agent_role": "claude.code",
    })
    assert redeemed["success"] is True
    assert redeemed["result"]["admission_ticket_id"] == ticket_id
    assert "objective" not in redeemed["result"]
