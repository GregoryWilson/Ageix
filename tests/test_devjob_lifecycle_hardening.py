"""
DevJob lifecycle hardening, conformed to the Sprint 21.1/21.5 event API.

Ports the sibling lifecycle-hardening behaviors (blocked/declined states,
evidence-gated scope revision, validation waiver, git-sync attach, completion
gate) onto the canonical DevJob event API: governed non-transition events are
recorded via `append_event` (append-only file store) and read back via
`list_events` (a list). Also pins the work_context relocation: assignment does
NOT require a Work Context; only DevWorker execution does.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models.agent_role import AgentRole
from services.devjob_registry_service import DevJobRegistryService

WORKER = "claude.code-worker-1"


def _assigned(registry: DevJobRegistryService, **kw) -> str:
    job = registry.create_job(
        title="A", objective="B", created_by="greg",
        status="assigned", assigned_to=WORKER, **kw,
    )
    return job.job_id


# ---------------------------------------------------------------------------
# Work-context relocation
# ---------------------------------------------------------------------------

def test_assign_job_does_not_require_work_context(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    draft = registry.create_job(title="A", objective="B", created_by="greg")
    # Deliberate assignment path: scope fields required, Work Context optional.
    assigned = registry.assign_job(
        draft.job_id,
        acceptance_criteria=["done"], allowed_paths=["src/"], prohibited_paths=["secrets/"],
        assigned_to=WORKER, actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR,
    )
    assert assigned.status == "assigned"
    assert assigned.work_context_id is None


def test_assign_job_still_requires_scope_fields(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    draft = registry.create_job(title="A", objective="B", created_by="greg")
    with pytest.raises(ValueError, match="devjob_assignment_requires_acceptance_criteria"):
        registry.assign_job(
            draft.job_id, allowed_paths=["src/"], prohibited_paths=["s/"],
            assigned_to=WORKER, actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR,
        )


# ---------------------------------------------------------------------------
# blocked / declined states with reason requirement
# ---------------------------------------------------------------------------

def test_blocked_requires_reason(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    registry.transition_job(job_id, "in_progress", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    with pytest.raises(ValueError, match="devjob_blocked_requires_reason"):
        registry.transition_job(job_id, "blocked", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    blocked = registry.transition_job(
        job_id, "blocked", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE, note="waiting upstream",
    )
    assert blocked.status == "blocked"
    assert blocked.lifecycle_history[-1]["note"] == "waiting upstream"


def test_declined_requires_reason(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    with pytest.raises(ValueError, match="devjob_declined_requires_reason"):
        registry.transition_job(job_id, "declined", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    declined = registry.transition_job(
        job_id, "declined", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE, note="out of scope",
    )
    assert declined.status == "declined"


def test_blocked_can_resume_to_in_progress(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    registry.transition_job(job_id, "in_progress", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    registry.transition_job(job_id, "blocked", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE, note="x")
    resumed = registry.transition_job(job_id, "in_progress", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    assert resumed.status == "in_progress"


# ---------------------------------------------------------------------------
# Governed events via the canonical event API
# ---------------------------------------------------------------------------

def test_scope_revision_is_evidence_gated_and_recorded_as_event(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry, allowed_paths=["src/"])
    with pytest.raises(ValueError, match="devjob_scope_revision_requires_reason"):
        registry.revise_scope(job_id, reason="", evidence_package_ids=["EVPKG-1"],
                              allowed_paths=["src/"], actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR)
    with pytest.raises(ValueError, match="devjob_scope_revision_requires_evidence"):
        registry.revise_scope(job_id, reason="widen", evidence_package_ids=[],
                              allowed_paths=["src/"], actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR)

    revised = registry.revise_scope(
        job_id, reason="widen scope", evidence_package_ids=["EVPKG-1"],
        allowed_paths=["src/", "lib/"], actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR,
    )
    assert revised.allowed_paths == ["src/", "lib/"]
    events = registry.list_events(job_id)
    scope_events = [e for e in events if e["event_type"] == "scope_revision"]
    assert len(scope_events) == 1
    assert scope_events[0]["metadata"]["evidence_package_ids"] == ["EVPKG-1"]
    assert scope_events[0]["metadata"]["before"]["allowed_paths"] == ["src/"]


def test_list_events_returns_list_of_governed_events(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    registry.attach_sync(job_id, branch="feature/x", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    events = registry.list_events(job_id)
    # Canonical event API: a list, not a dict.
    assert isinstance(events, list)
    assert any(e["event_type"] == "git_sync_attached" for e in events)


def test_validation_waiver_requires_governance(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    with pytest.raises(ValueError, match="devjob_validation_waiver_requires_governance"):
        registry.record_validation_waiver(job_id, reason="ok", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    waived = registry.record_validation_waiver(job_id, reason="hotfix", actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR)
    assert any(e["event_type"] == "validation_waiver" for e in registry.list_events(waived.job_id))


# ---------------------------------------------------------------------------
# Completion gate
# ---------------------------------------------------------------------------

def _to_reviewed(registry: DevJobRegistryService, job_id: str, **result_kw) -> None:
    registry.transition_job(job_id, "in_progress", actor_id=WORKER, actor_role=AgentRole.CLAUDE_CODE)
    registry.submit_result(job_id=job_id, submitted_by=WORKER, actor_role=AgentRole.CLAUDE_CODE, **result_kw)
    registry.transition_job(job_id, "reviewed", actor_id="greg", actor_role=AgentRole.UNKNOWN)


def test_completion_requires_validation_or_waiver(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    _to_reviewed(registry, job_id, branch_name="feature/x")  # git sync present, no validation
    with pytest.raises(ValueError, match="devjob_completion_requires_validation_or_waiver"):
        registry.transition_job(job_id, "completed", actor_id="greg", actor_role=AgentRole.UNKNOWN)
    # A governed waiver satisfies the validation half of the gate.
    registry.record_validation_waiver(job_id, reason="hotfix", actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR)
    completed = registry.transition_job(job_id, "completed", actor_id="greg", actor_role=AgentRole.UNKNOWN)
    assert completed.status == "completed"


def test_completion_requires_git_sync_reference(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    _to_reviewed(registry, job_id, validation_run_id="VALRUN-1")  # validation present, no git sync
    with pytest.raises(ValueError, match="devjob_completion_requires_git_sync_reference"):
        registry.transition_job(job_id, "completed", actor_id="greg", actor_role=AgentRole.UNKNOWN)
    registry.attach_sync(job_id, branch="feature/x", actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR)
    completed = registry.transition_job(job_id, "completed", actor_id="greg", actor_role=AgentRole.UNKNOWN)
    assert completed.status == "completed"


def test_completion_succeeds_with_result_validation_and_branch(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_id = _assigned(registry)
    _to_reviewed(registry, job_id, validation_run_id="VALRUN-1", branch_name="feature/x")
    completed = registry.transition_job(job_id, "completed", actor_id="greg", actor_role=AgentRole.UNKNOWN)
    assert completed.status == "completed"
