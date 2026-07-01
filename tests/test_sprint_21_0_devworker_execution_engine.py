from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from models.agent_role import AgentRole
from services.devjob_registry_service import DevJobRegistryService
from services.devjob_lifecycle_service import authorize_transition
from services.devworker_execution_service import (
    DevWorkerContext,
    DevWorkerExecutionResult,
    DevWorkerExecutionService,
)

WORKER_ID = "claude.code-devworker-1"
ACTOR_ROLE = AgentRole.CLAUDE_CODE

MINIMAL_DIFF = """\
diff --git a/src/example.py b/src/example.py
index abc1234..def5678 100644
--- a/src/example.py
+++ b/src/example.py
@@ -1,2 +1,2 @@
 def hello():
-    pass
+    return "world"
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _MockGit:
    def __init__(self, diff_output: str) -> None:
        self._diff = diff_output

    def diff(self, *_args: str) -> str:
        return self._diff


def _write_workctx(tmp_path: Path, work_context_id: str) -> None:
    """Persist a minimal WORKCTX package under .ageix/architecture/work_context/."""
    pkg_dir = tmp_path / ".ageix" / "architecture" / "work_context" / work_context_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id,
            "project_id": "Ageix",
            "work_summary": "Test work context",
            "guidance_context": {
                "summary_first": True,
                "package_count": 0,
                "packages": [],
            },
            "governing_principles": [],
            "active_intent": [],
            "related_adrs": [],
        }),
        encoding="utf-8",
    )


def _write_evidence_package(tmp_path: Path, package_id: str) -> None:
    """Persist a minimal evidence package under .ageix/evidence_packages/."""
    pkg_dir = tmp_path / ".ageix" / "evidence_packages" / package_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "package_id": package_id,
            "objective": "Test evidence",
            "primary_evidence": [],
            "supporting_evidence": [],
            "validation_evidence": [],
        }),
        encoding="utf-8",
    )


def _make_assigned_job(
    tmp_path: Path,
    *,
    work_context_id: str,
    allowed_paths: list[str] | None = None,
    prohibited_paths: list[str] | None = None,
    evidence_package_ids: list[str] | None = None,
    worker_id: str = WORKER_ID,
) -> str:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Test DevJob",
        objective="Implement test feature.",
        instructions=["Write the implementation."],
        acceptance_criteria=["Tests pass."],
        allowed_paths=allowed_paths if allowed_paths is not None else ["src/"],
        prohibited_paths=prohibited_paths or [],
        work_context_id=work_context_id,
        evidence_package_ids=evidence_package_ids or [],
        created_by="greg",
        status="assigned",
        assigned_to=worker_id,
    )
    return job.job_id


def _make_service(tmp_path: Path, *, mock_diff: str = MINIMAL_DIFF) -> DevWorkerExecutionService:
    svc = DevWorkerExecutionService(tmp_path)
    svc._git = _MockGit(mock_diff)
    return svc


# ---------------------------------------------------------------------------
# Authorized execution — load_context returns a valid bundle
# ---------------------------------------------------------------------------

def test_load_context_returns_context_bundle(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-TESTTEST0001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)

    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    assert ctx.job.job_id == job_id
    assert ctx.workctx["work_context_id"] == work_context_id
    assert isinstance(ctx.guidance_context, dict)
    assert isinstance(ctx.allowed_paths, list)
    assert isinstance(ctx.prohibited_paths, list)
    assert isinstance(ctx.evidence, list)


def test_load_context_populates_guidance_context_from_workctx(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-TESTTEST0002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)

    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    assert ctx.guidance_context.get("summary_first") is True


def test_load_context_loads_referenced_evidence_packages(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-TESTTEST0003"
    pkg_id = "EVPKG-TESTTEST00001"
    _write_workctx(tmp_path, work_context_id)
    _write_evidence_package(tmp_path, pkg_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=[pkg_id],
    )

    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    assert len(ctx.evidence) == 1
    assert ctx.evidence[0]["package_id"] == pkg_id


def test_load_context_does_not_silently_skip_missing_evidence(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-TESTTEST0004"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-DOESNOTEXIST01"],
    )

    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    # Not silently skipped: the missing package is tracked and warned about.
    assert ctx.evidence == []
    assert ctx.missing_evidence_package_ids == ["EVPKG-DOESNOTEXIST01"]
    assert ctx.loaded_evidence_package_ids == []
    assert len(ctx.warnings) == 1
    assert ctx.warnings[0].code == "evidence_package_missing"
    assert ctx.warnings[0].related_object_id == "EVPKG-DOESNOTEXIST01"


# ---------------------------------------------------------------------------
# Unauthorized execution denial
# ---------------------------------------------------------------------------

def test_load_context_denies_non_devworker_role(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-AUTHTEST0001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)

    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_role_not_authorized"):
        svc.load_context(job_id, worker_id=WORKER_ID, actor_role=AgentRole.CLAUDE_AI)


def test_load_context_denies_governance_role(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-AUTHTEST0002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)

    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_role_not_authorized"):
        svc.load_context(job_id, worker_id=WORKER_ID, actor_role=AgentRole.AGEIX_CHAIR)


def test_load_context_denies_wrong_worker_id(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-AUTHTEST0003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)

    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_not_assigned_to_this_job"):
        svc.load_context(job_id, worker_id="claude.code-other-worker", actor_role=ACTOR_ROLE)


def test_load_context_denies_draft_job(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-AUTHTEST0004"
    _write_workctx(tmp_path, work_context_id)
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Draft Job",
        objective="x",
        work_context_id=work_context_id,
        created_by="greg",
        status="draft",
    )

    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_job_not_assigned"):
        svc.load_context(job.job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)


def test_load_context_denies_unknown_job_id(tmp_path: Path) -> None:
    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_job_load_failed"):
        svc.load_context("DEVJOB-DOESNOTEXIST1", worker_id=WORKER_ID, actor_role=ACTOR_ROLE)


# ---------------------------------------------------------------------------
# Missing Work Context denial
# ---------------------------------------------------------------------------

def test_load_context_raises_when_job_has_no_work_context_id(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="No WORKCTX",
        objective="x",
        created_by="greg",
        status="assigned",
        assigned_to=WORKER_ID,
        work_context_id=None,
    )

    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_work_context_required"):
        svc.load_context(job.job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)


def test_load_context_raises_when_work_context_file_missing(tmp_path: Path) -> None:
    job_id = _make_assigned_job(tmp_path, work_context_id="WORKCTX-NOTEXIST00001")

    svc = DevWorkerExecutionService(tmp_path)
    with pytest.raises(ValueError, match="devworker_work_context_missing"):
        svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)


# ---------------------------------------------------------------------------
# Repository path enforcement
# ---------------------------------------------------------------------------

def test_validate_path_allows_path_within_allowed_prefix(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATHTEST0001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        allowed_paths=["src/", "tests/"],
    )
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    svc.validate_path("src/module.py", ctx)
    svc.validate_path("tests/test_module.py", ctx)


def test_validate_path_denies_path_outside_allowed(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATHTEST0002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        allowed_paths=["src/"],
    )
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    with pytest.raises(ValueError, match="devworker_path_not_authorized"):
        svc.validate_path("config.yaml", ctx)


def test_validate_path_denies_prohibited_even_when_allowed(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATHTEST0003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        allowed_paths=["src/", "infra/"],
        prohibited_paths=["infra/secrets/"],
    )
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    with pytest.raises(ValueError, match="devworker_path_prohibited"):
        svc.validate_path("infra/secrets/key.pem", ctx)


def test_validate_path_empty_allowed_permits_all_non_prohibited(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATHTEST0004"
    _write_workctx(tmp_path, work_context_id)
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Open Scope",
        objective="x",
        work_context_id=work_context_id,
        allowed_paths=[],
        prohibited_paths=["secrets/"],
        created_by="greg",
        status="assigned",
        assigned_to=WORKER_ID,
    )
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job.job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    svc.validate_path("app.py", ctx)

    with pytest.raises(ValueError, match="devworker_path_prohibited"):
        svc.validate_path("secrets/token.txt", ctx)


# ---------------------------------------------------------------------------
# Patch artifact generation
# ---------------------------------------------------------------------------

def test_create_patch_artifact_produces_governed_patch(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATCHTEST001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)

    assert patch["patch_id"].startswith("PATCH-")
    assert patch["line_count"] > 0
    patch_dir = tmp_path / ".ageix" / "patches" / patch["patch_id"]
    assert (patch_dir / "patch.diff").exists()
    assert (patch_dir / "metadata.json").exists()


def test_create_patch_artifact_embeds_job_id_in_metadata(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATCHTEST002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)
    meta_path = tmp_path / ".ageix" / "patches" / patch["patch_id"] / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta["metadata"]["job_id"] == job_id
    assert meta["metadata"]["work_context_id"] == work_context_id


def test_create_patch_artifact_registers_as_artifact(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-PATCHTEST003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)

    assert patch.get("artifact_id") is not None
    assert str(patch["artifact_id"]).startswith("ART-")


# ---------------------------------------------------------------------------
# Result submission
# ---------------------------------------------------------------------------

def test_submit_result_moves_job_to_submitted(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-RESTEST0001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)
    outcome = svc.submit_result(
        ctx, patch["patch_id"],
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        changed_files=["src/example.py"],
    )

    assert outcome["job"]["status"] == "submitted"
    assert outcome["result"]["patch_id"] == patch["patch_id"]


def test_submit_result_carries_reference_fields_only(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-RESTEST0002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)
    outcome = svc.submit_result(
        ctx, patch["patch_id"],
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        changed_files=["src/a.py", "src/b.py"],
        artifact_ids=["ART-EXTERNAL1234"],
        validation_run_id="VALRUN-XYZ",
        branch_name="feature/test-branch",
        result_summary="Implementation complete.",
    )

    result = outcome["result"]
    assert result["patch_id"] == patch["patch_id"]
    assert "ART-EXTERNAL1234" in result["artifact_ids"]
    assert result["validation_run_id"] == "VALRUN-XYZ"
    assert result["branch_name"] == "feature/test-branch"


def test_submit_result_transitions_assigned_through_in_progress(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-RESTEST0003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)
    svc.submit_result(ctx, patch["patch_id"], worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    registry = DevJobRegistryService(tmp_path)
    job = registry.get_job(job_id)
    statuses = [h["to_status"] for h in job.lifecycle_history]
    assert "in_progress" in statuses
    assert "submitted" in statuses


# ---------------------------------------------------------------------------
# Governance preservation
# ---------------------------------------------------------------------------

def test_devworker_cannot_complete_job(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-GOVTEST0001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)
    svc.submit_result(ctx, patch["patch_id"], worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    # Advance to reviewed via an authorized actor (greg) so we can test the
    # completion boundary — the transition from submitted → reviewed requires a
    # reviewer, not the DevWorker.
    registry = DevJobRegistryService(tmp_path)
    registry.transition_job(job_id, "reviewed", actor_id="greg", actor_role=AgentRole.UNKNOWN)

    with pytest.raises(ValueError, match="devjob_transition_requires_greg_or_governance"):
        registry.transition_job(job_id, "completed", actor_id=WORKER_ID, actor_role=ACTOR_ROLE)


def test_devworker_cannot_mark_reviewed(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-GOVTEST0002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    patch = svc.create_patch_artifact(MINIMAL_DIFF, ctx)
    svc.submit_result(ctx, patch["patch_id"], worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_transition_requires_reviewer_or_greg"):
        registry.transition_job(job_id, "reviewed", actor_id=WORKER_ID, actor_role=ACTOR_ROLE)


def test_devworker_cannot_assign_job(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-GOVTEST0003"
    _write_workctx(tmp_path, work_context_id)
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Another Job",
        objective="x",
        work_context_id=work_context_id,
        created_by="greg",
        status="draft",
    )

    with pytest.raises(ValueError, match="devjob_transition_requires_creator_or_governance"):
        registry.transition_job(
            job.job_id, "assigned",
            actor_id=WORKER_ID,
            actor_role=ACTOR_ROLE,
        )


# ---------------------------------------------------------------------------
# Full execute() orchestration
# ---------------------------------------------------------------------------

def test_execute_returns_submitted_result(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-EXECTEST001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )

    assert result.status == "submitted"
    assert result.job_id == job_id
    assert result.patch_id is not None and result.patch_id.startswith("PATCH-")
    assert result.changed_files == ["src/example.py"]
    assert result.result["job"]["status"] == "submitted"


def test_execute_blocked_when_implementation_produces_no_diff(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-EXECTEST002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path, mock_diff="")

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: [],
    )

    assert result.status == "blocked"
    assert result.error == "devworker_no_changes_detected"
