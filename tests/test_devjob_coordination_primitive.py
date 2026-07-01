from __future__ import annotations

from pathlib import Path

import pytest

from ageix_mcp.tool_definitions import MCP_TOOL_DEFINITIONS
from models.agent_role import AgentRole
from models.capability_request import CapabilityRequest
from models.devjob import DevJob
from models.devjob_result import DevJobResult
from services.capabilities.devjob_capabilities import register_capabilities
from services.capability_execution_service import CapabilityExecutionService
from services.devjob_registry_service import DevJobRegistryService

DEVJOB_CAPABILITY_IDS = (
    "devjob.create",
    "devjob.list",
    "devjob.get",
    "devjob.result.submit",
)


def _tool_by_capability() -> dict[str, object]:
    return {tool.capability_id: tool for tool in MCP_TOOL_DEFINITIONS}


def _execute(tmp_path: Path, capability_id: str, arguments: dict) -> dict:
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="sess-worker",
        agent_id="claude.code",
        arguments=arguments,
    ))
    return {"success": response.success, "result": response.result, "error": response.error}


# --- Model-level tests -----------------------------------------------------

def test_devjob_stable_id_generation() -> None:
    first = DevJob(title="A", objective="B", created_by="greg")
    second = DevJob(title="A", objective="B", created_by="greg")
    assert first.job_id.startswith("DEVJOB-")
    assert second.job_id.startswith("DEVJOB-")
    assert first.job_id != second.job_id


def test_devjob_result_stable_id_generation() -> None:
    first = DevJobResult(job_id="DEVJOB-AAAAAAAAAAAA", submitted_by="claude.code")
    second = DevJobResult(job_id="DEVJOB-AAAAAAAAAAAA", submitted_by="claude.code")
    assert first.result_id.startswith("DEVJOBRESULT-")
    assert first.result_id != second.result_id


def test_devjob_default_status_is_draft() -> None:
    job = DevJob(title="A", objective="B", created_by="greg")
    assert job.status == "draft"


# --- Registry persistence tests --------------------------------------------

def test_create_job_persists_under_ageix_devjobs(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(title="Implement thing", objective="Ship the thing", created_by="greg")

    devjob_root = tmp_path / ".ageix" / "devjobs"
    assert (devjob_root / "index.json").exists()
    assert (devjob_root / job.job_id / "job.json").exists()


def test_create_job_requires_title_and_objective(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_title_required"):
        registry.create_job(title="", objective="x", created_by="greg")
    with pytest.raises(ValueError, match="devjob_objective_required"):
        registry.create_job(title="x", objective="", created_by="greg")


def test_create_job_rejects_non_initial_status(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_initial_status_must_be_draft_or_assigned"):
        registry.create_job(title="x", objective="y", created_by="greg", status="completed")


def test_create_job_assigned_requires_assigned_to(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_assigned_status_requires_assigned_to"):
        registry.create_job(title="x", objective="y", created_by="greg", status="assigned")


def test_index_maintains_all_created_jobs(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job_one = registry.create_job(title="One", objective="Do one", created_by="greg")
    job_two = registry.create_job(title="Two", objective="Do two", created_by="greg")

    index = registry._read_index()
    ids = {item["job_id"] for item in index}
    assert {job_one.job_id, job_two.job_id} <= ids


def test_get_job_unknown_id_raises(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_not_found"):
        registry.get_job("DEVJOB-DOES-NOT-EXIST")


def test_list_jobs_filters_and_paginates(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    for i in range(3):
        registry.create_job(title=f"Job {i}", objective="x", created_by="greg", repo_target="Ageix")
    registry.create_job(title="Other repo", objective="x", created_by="greg", repo_target="OtherRepo")

    result = registry.list_jobs(repo_target="Ageix")
    assert result["total_count"] == 3
    assert result["count"] == 3

    paged = registry.list_jobs(repo_target="Ageix", limit=2, offset=1)
    assert paged["count"] == 2
    assert paged["limit"] == 2
    assert paged["offset"] == 1


# --- Lifecycle transition tests --------------------------------------------

def test_assigned_devworker_can_progress_job_to_submitted(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Implement", objective="Ship it", created_by="greg",
        status="assigned", assigned_to="claude.code-worker-1",
    )
    registry.transition_job(job.job_id, "in_progress", actor_id="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)
    updated = registry.transition_job(job.job_id, "submitted", actor_id="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)
    assert updated.status == "submitted"
    assert len(updated.lifecycle_history) == 3  # created, in_progress, submitted


def test_invalid_transition_rejected(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(title="A", objective="B", created_by="greg")
    with pytest.raises(ValueError, match="invalid_devjob_state_transition_draft_to_submitted"):
        registry.transition_job(job.job_id, "submitted", actor_id="greg", actor_role=AgentRole.UNKNOWN)


def test_unassigned_devworker_cannot_start_job(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="A", objective="B", created_by="greg",
        status="assigned", assigned_to="claude.code-worker-1",
    )
    with pytest.raises(ValueError, match="devjob_transition_requires_assigned_devworker"):
        registry.transition_job(job.job_id, "in_progress", actor_id="claude.code-worker-2", actor_role=AgentRole.CLAUDE_CODE)


def test_only_greg_or_governance_can_complete_job(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="A", objective="B", created_by="greg",
        status="assigned", assigned_to="claude.code-worker-1",
    )
    registry.transition_job(job.job_id, "in_progress", actor_id="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)
    # Submit a result carrying validation + git-sync references so the
    # completion gate is satisfied (lifecycle hardening).
    registry.submit_result(
        job_id=job.job_id, submitted_by="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE,
        validation_run_id="VALRUN-XYZ", branch_name="feature/thing",
    )
    registry.transition_job(job.job_id, "reviewed", actor_id="greg", actor_role=AgentRole.UNKNOWN)

    # Authority is checked before the completion gate: an unauthorized actor is
    # rejected on authority regardless of the gate.
    with pytest.raises(ValueError, match="devjob_transition_requires_greg_or_governance"):
        registry.transition_job(job.job_id, "completed", actor_id="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)

    completed = registry.transition_job(job.job_id, "completed", actor_id="greg", actor_role=AgentRole.UNKNOWN)
    assert completed.status == "completed"


def test_reviewer_role_can_mark_reviewed(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="A", objective="B", created_by="greg",
        status="assigned", assigned_to="claude.code-worker-1",
    )
    registry.transition_job(job.job_id, "in_progress", actor_id="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)
    registry.submit_result(job_id=job.job_id, submitted_by="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)
    reviewed = registry.transition_job(job.job_id, "reviewed", actor_id="reviewer-1", actor_role=AgentRole.LEX)
    assert reviewed.status == "reviewed"


# --- Result submission tests -------------------------------------------------

def test_submit_result_carries_reference_fields_only(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="A", objective="B", created_by="greg",
        status="assigned", assigned_to="claude.code-worker-1",
    )
    registry.transition_job(job.job_id, "in_progress", actor_id="claude.code-worker-1", actor_role=AgentRole.CLAUDE_CODE)
    outcome = registry.submit_result(
        job_id=job.job_id,
        result_summary="Implemented the thing.",
        submitted_by="claude.code-worker-1",
        actor_role=AgentRole.CLAUDE_CODE,
        patch_id="PATCH-ABCDEF123456",
        artifact_ids=["ART-1", "ART-2"],
        validation_run_id="VALRUN-XYZ",
        branch_name="feature/devjob-thing",
        public_branch_or_pr="https://example.invalid/pr/1",
        changed_files=["foo.py", "bar.py"],
    )
    assert outcome["job"]["status"] == "submitted"
    result = outcome["result"]
    assert result["patch_id"] == "PATCH-ABCDEF123456"
    assert result["artifact_ids"] == ["ART-1", "ART-2"]
    assert result["validation_run_id"] == "VALRUN-XYZ"
    assert result["branch_name"] == "feature/devjob-thing"

    results = registry.list_results(job.job_id)
    assert len(results) == 1
    assert results[0]["job_id"] == job.job_id


def test_devjob_carries_conversation_and_handoff_references(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="A", objective="B", created_by="greg",
        conversation_id="CONV-ABCDEF123456",
        handoff_id="HANDOFF-ABCDEF123456",
        work_context_id="WORKCTX-ABCDEF123456",
        evidence_package_ids=["EVPKG-1"],
        validation_profile_ids=["VALPROF-1"],
    )
    fetched = registry.get_job(job.job_id)
    assert fetched.conversation_id == "CONV-ABCDEF123456"
    assert fetched.handoff_id == "HANDOFF-ABCDEF123456"
    assert fetched.work_context_id == "WORKCTX-ABCDEF123456"
    assert fetched.evidence_package_ids == ["EVPKG-1"]
    assert fetched.validation_profile_ids == ["VALPROF-1"]


# --- Cleanup utility ---------------------------------------------------------

def test_delete_job_removes_record_and_index_entry(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(title="A", objective="B", created_by="greg")
    registry.delete_job(job.job_id)
    with pytest.raises(ValueError, match="devjob_not_found"):
        registry.get_job(job.job_id)
    assert not (tmp_path / ".ageix" / "devjobs" / job.job_id).exists()


def test_no_unintended_repository_mutation(tmp_path: Path) -> None:
    before = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")}
    registry = DevJobRegistryService(tmp_path)
    registry.create_job(title="A", objective="B", created_by="greg")
    after = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")}
    new_paths = after - before
    assert all(path == ".ageix" or path.startswith(".ageix/devjobs") for path in new_paths)


# --- Capability + MCP catalog tests ------------------------------------------

def test_catalog_exposes_devjob_tools() -> None:
    tools = _tool_by_capability()
    for capability_id in DEVJOB_CAPABILITY_IDS:
        assert capability_id in tools
        assert tools[capability_id].name == f"ageix.{capability_id}"
        assert tools[capability_id].description
        assert tools[capability_id].category == "devjob"


def test_devjob_capability_plugin_registers_handlers(tmp_path: Path) -> None:
    registered = {definition.capability_id: handler for definition, handler in register_capabilities(tmp_path)}
    for capability_id in DEVJOB_CAPABILITY_IDS:
        assert capability_id in registered
        assert callable(registered[capability_id])


def test_devjob_lifecycle_through_capability_execution(tmp_path: Path) -> None:
    created = _execute(tmp_path, "devjob.create", {
        "client_id": "ageix-connector-claude-ai",
        "agent_role": "claude.ai",
        "title": "Implement DevJob primitive",
        "objective": "Ship the first DevJob coordination primitive.",
        "status": "assigned",
        "assigned_to": "ageix-connector-claude-code",
        "created_by": "greg",
    })
    assert created["success"] is True
    job_id = created["result"]["job_id"]
    assert created["result"]["status"] == "assigned"

    fetched = _execute(tmp_path, "devjob.get", {"client_id": "ageix-connector-claude-code", "job_id": job_id})
    assert fetched["success"] is True
    assert fetched["result"]["job_id"] == job_id

    listed = _execute(tmp_path, "devjob.list", {"client_id": "ageix-connector-claude-code", "status": "assigned"})
    assert listed["success"] is True
    assert listed["result"]["total_count"] == 1

    # in_progress is not yet exposed as its own MCP capability in this sprint;
    # move the job there at the service layer before exercising result.submit.
    DevJobRegistryService(tmp_path).transition_job(
        job_id, "in_progress", actor_id="ageix-connector-claude-code", actor_role=AgentRole.CLAUDE_CODE,
    )

    submitted = _execute(tmp_path, "devjob.result.submit", {
        "client_id": "ageix-connector-claude-code",
        "agent_role": "claude.code",
        "actor_id": "ageix-connector-claude-code",
        "job_id": job_id,
        "result_summary": "Implemented the DevJob primitive.",
        "patch_id": "PATCH-ABCDEF123456",
    })
    assert submitted["success"] is True
    assert submitted["result"]["job"]["status"] == "submitted"

    refetched = _execute(tmp_path, "devjob.get", {"client_id": "ageix-connector-claude-code", "job_id": job_id})
    assert refetched["result"]["status"] == "submitted"


def test_devjob_get_unknown_id_returns_error(tmp_path: Path) -> None:
    result = _execute(tmp_path, "devjob.get", {"client_id": "ageix-connector-claude-code", "job_id": "DEVJOB-DOES-NOT-EXIST"})
    assert result["success"] is False
    assert result["error"] == "devjob_not_found"


def test_devjob_create_missing_fields_returns_error(tmp_path: Path) -> None:
    result = _execute(tmp_path, "devjob.create", {"client_id": "ageix-connector-claude-ai"})
    assert result["success"] is False
    assert result["error"] == "title_required"
