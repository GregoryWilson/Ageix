"""
Regression guard for the DevJob work_context enforcement boundary.

work_context_id is required for EXECUTION-READY DevJobs at the point a DevWorker
actually loads context — NOT at DevJob creation/assignment. Requiring it in
DevJobRegistryService.create_job() breaks generic DevJob assignment, Worker
Admission, the Worker Launcher, the CLI, and existing fixtures, none of which
supply a Work Context.

These tests pin the boundary: creation stays permissive; load_context enforces.
If a future change moves the requirement back into create_job(), the creation
tests below will fail loudly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models.agent_role import AgentRole
from services.devjob_registry_service import DevJobRegistryService
from services.devworker_execution_service import DevWorkerExecutionService

WORKER = "claude-code-worker-1"
ROLE = AgentRole.CLAUDE_CODE


# ---------------------------------------------------------------------------
# Creation must NOT require work_context_id
# ---------------------------------------------------------------------------

def test_create_draft_without_work_context(tmp_path: Path) -> None:
    job = DevJobRegistryService(tmp_path).create_job(
        title="Draft", objective="x", created_by="greg",
    )
    assert job.status == "draft"
    assert job.work_context_id is None


def test_create_assigned_without_work_context(tmp_path: Path) -> None:
    # Generic DevJob assignment (admission/launcher/CLI/fixtures) must work
    # without a Work Context.
    job = DevJobRegistryService(tmp_path).create_job(
        title="Assigned", objective="x", created_by="greg",
        status="assigned", assigned_to=WORKER,
    )
    assert job.status == "assigned"
    assert job.assigned_to == WORKER
    assert job.work_context_id is None


def test_assigned_job_persists_and_reloads_without_work_context(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Assigned", objective="x", created_by="greg",
        status="assigned", assigned_to=WORKER,
    )
    reloaded = registry.get_job(job.job_id)
    assert reloaded.work_context_id is None
    assert reloaded.status == "assigned"


# ---------------------------------------------------------------------------
# Enforcement lives at the execution / context-loading boundary
# ---------------------------------------------------------------------------

def test_load_context_requires_work_context(tmp_path: Path) -> None:
    job = DevJobRegistryService(tmp_path).create_job(
        title="Assigned", objective="x", created_by="greg",
        status="assigned", assigned_to=WORKER,
    )
    # The missing-work-context failure happens at load_context time, not create.
    with pytest.raises(ValueError, match="devworker_work_context_required"):
        DevWorkerExecutionService(tmp_path).load_context(
            job.job_id, worker_id=WORKER, actor_role=ROLE,
        )
