from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.agent_role import AgentRole
from models.execution_warning import ExecutionWarning
from services.devjob_registry_service import DevJobRegistryService
from services.devworker_execution_service import DevWorkerExecutionService

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
    pkg_dir = tmp_path / ".ageix" / "architecture" / "work_context" / work_context_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id,
            "project_id": "Ageix",
            "work_summary": "Test work context",
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )


def _write_evidence_package(tmp_path: Path, package_id: str) -> None:
    pkg_dir = tmp_path / ".ageix" / "evidence_packages" / package_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(
        json.dumps({
            "package_id": package_id,
            "objective": "Test evidence",
            "primary_evidence": [],
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
        acceptance_criteria=["Tests pass."],
        allowed_paths=allowed_paths if allowed_paths is not None else ["src/"],
        # Default to a non-empty prohibited_paths so the DevJob satisfies the
        # assignment invariant; explicit overrides (including []) are preserved.
        prohibited_paths=prohibited_paths if prohibited_paths is not None else ["secrets/"],
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
# 1. Structured execution warnings
# ---------------------------------------------------------------------------

def test_execution_warning_model_carries_structured_fields() -> None:
    warning = ExecutionWarning(
        code="evidence_package_missing",
        severity="warning",
        message="thing missing",
        related_object_id="EVPKG-XYZ",
        metadata={"job_id": "DEVJOB-1"},
    )
    payload = warning.to_dict()
    assert payload["code"] == "evidence_package_missing"
    assert payload["severity"] == "warning"
    assert payload["message"] == "thing missing"
    assert payload["related_object_id"] == "EVPKG-XYZ"
    assert payload["metadata"]["job_id"] == "DEVJOB-1"


def test_execution_warning_defaults_severity_to_warning() -> None:
    warning = ExecutionWarning(code="c", message="m")
    assert warning.severity == "warning"
    assert warning.related_object_id is None
    assert warning.metadata == {}


# ---------------------------------------------------------------------------
# 2. Missing evidence must not be silent
# ---------------------------------------------------------------------------

def test_missing_evidence_records_structured_warning(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-MISS00000001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-MISSING00001"],
    )
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    assert ctx.missing_evidence_package_ids == ["EVPKG-MISSING00001"]
    assert len(ctx.warnings) == 1
    w = ctx.warnings[0]
    assert w.code == "evidence_package_missing"
    assert w.severity == "warning"
    assert w.related_object_id == "EVPKG-MISSING00001"


def test_partial_evidence_loads_present_and_warns_on_missing(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-MISS00000002"
    present = "EVPKG-PRESENT00001"
    _write_workctx(tmp_path, work_context_id)
    _write_evidence_package(tmp_path, present)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=[present, "EVPKG-ABSENT000001"],
    )
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    assert ctx.loaded_evidence_package_ids == [present]
    assert ctx.missing_evidence_package_ids == ["EVPKG-ABSENT000001"]
    assert len(ctx.evidence) == 1
    assert len(ctx.warnings) == 1


def test_missing_evidence_does_not_fail_execution(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-MISS00000003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-ABSENT000002"],
    )
    svc = _make_service(tmp_path)
    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )
    # Execution continues to a submitted result despite the missing evidence.
    assert result.status == "submitted"


# ---------------------------------------------------------------------------
# 3. Execution summary
# ---------------------------------------------------------------------------

def test_execution_summary_contains_required_fields(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SUMM00000001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-ABSENT000003"],
    )
    svc = _make_service(tmp_path)
    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )
    summary = result.to_summary()

    for key in (
        "status", "worker_id", "job_id", "work_context_id",
        "loaded_evidence_package_ids", "missing_evidence_package_ids",
        "changed_files", "patch_id", "warnings", "blocked_reason",
    ):
        assert key in summary, f"missing summary key: {key}"

    assert summary["status"] == "submitted"
    assert summary["worker_id"] == WORKER_ID
    assert summary["job_id"] == job_id
    assert summary["work_context_id"] == work_context_id
    assert summary["missing_evidence_package_ids"] == ["EVPKG-ABSENT000003"]
    assert summary["changed_files"] == ["src/example.py"]
    assert summary["patch_id"] is not None
    assert len(summary["warnings"]) == 1
    assert summary["blocked_reason"] is None


def test_execution_summary_reports_missing_evidence(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SUMM00000002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-GONE00000001", "EVPKG-GONE00000002"],
    )
    svc = _make_service(tmp_path)
    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )
    summary = result.to_summary()
    assert set(summary["missing_evidence_package_ids"]) == {
        "EVPKG-GONE00000001", "EVPKG-GONE00000002",
    }
    assert len(summary["warnings"]) == 2


# ---------------------------------------------------------------------------
# 4. Missing evidence appears in DevJob result metadata
# ---------------------------------------------------------------------------

def test_missing_evidence_appears_in_devjob_result_metadata(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-RESMETA00001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-NOTHERE00001"],
    )
    svc = _make_service(tmp_path)
    svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )

    registry = DevJobRegistryService(tmp_path)
    results = registry.list_results(job_id)
    assert len(results) == 1
    submitted = results[0]

    assert submitted["metadata"]["missing_evidence_package_ids"] == ["EVPKG-NOTHERE00001"]
    assert submitted["metadata"]["warning_count"] == 1
    assert len(submitted["warnings"]) == 1
    assert submitted["warnings"][0]["code"] == "evidence_package_missing"


def test_successful_execution_with_warnings_still_submits_references(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-RESMETA00002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-MISSINGREF01"],
    )
    svc = _make_service(tmp_path)
    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )

    assert result.status == "submitted"
    assert result.patch_id is not None
    assert result.result["job"]["status"] == "submitted"
    assert result.result["result"]["patch_id"] == result.patch_id
    # Warnings did not suppress the reference submission.
    assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# 5. Fatal context problems remain explicit
# ---------------------------------------------------------------------------

def test_missing_work_context_remains_fatal(tmp_path: Path) -> None:
    job_id = _make_assigned_job(tmp_path, work_context_id="WORKCTX-NONEXIST0001")
    svc = _make_service(tmp_path)
    with pytest.raises(ValueError, match="devworker_work_context_missing"):
        svc.execute(
            job_id,
            worker_id=WORKER_ID,
            actor_role=ACTOR_ROLE,
            implementation_fn=lambda ctx: ["src/example.py"],
        )


def test_unauthorized_worker_remains_denied(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-FATAL0000001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    with pytest.raises(ValueError, match="devworker_role_not_authorized"):
        svc.execute(
            job_id,
            worker_id=WORKER_ID,
            actor_role=AgentRole.CLAUDE_AI,
            implementation_fn=lambda ctx: ["src/example.py"],
        )


def test_wrong_worker_id_remains_denied(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-FATAL0000002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path)
    with pytest.raises(ValueError, match="devworker_not_assigned_to_this_job"):
        svc.execute(
            job_id,
            worker_id="claude.code-imposter",
            actor_role=ACTOR_ROLE,
            implementation_fn=lambda ctx: ["src/example.py"],
        )


def test_prohibited_path_violation_remains_explicit(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-FATAL0000003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        allowed_paths=["src/", "infra/"],
        prohibited_paths=["infra/secrets/"],
    )
    svc = _make_service(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)
    with pytest.raises(ValueError, match="devworker_path_prohibited"):
        svc.validate_path("infra/secrets/key.pem", ctx)


# ---------------------------------------------------------------------------
# 6. Blocked execution surfaces through append-only DevJob events
# ---------------------------------------------------------------------------

def test_blocked_execution_records_devjob_event(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-BLOCK0000001"
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

    registry = DevJobRegistryService(tmp_path)
    events = registry.list_events(job_id)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "execution_blocked"
    assert event["reason"] == "devworker_no_changes_detected"
    assert event["actor_id"] == WORKER_ID
    assert any(w["code"] == "devworker_no_changes_detected" for w in event["warnings"])


def test_blocked_execution_summary_carries_reason(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-BLOCK0000002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path, mock_diff="")

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: [],
    )
    summary = result.to_summary()
    assert summary["status"] == "blocked"
    assert summary["blocked_reason"] == "devworker_no_changes_detected"
    assert summary["patch_id"] is None


def test_blocked_execution_does_not_advance_lifecycle(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-BLOCK0000003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    svc = _make_service(tmp_path, mock_diff="")

    svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: [],
    )

    registry = DevJobRegistryService(tmp_path)
    job = registry.get_job(job_id)
    # Blocked execution records an event but must not submit or advance state.
    assert job.status == "assigned"
    assert registry.list_results(job_id) == []


# ---------------------------------------------------------------------------
# 7. Append-only event surface integrity
# ---------------------------------------------------------------------------

def test_append_event_requires_existing_job(tmp_path: Path) -> None:
    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_not_found"):
        registry.append_event(
            job_id="DEVJOB-DOESNOTEXIST1",
            event_type="execution_blocked",
            actor_id=WORKER_ID,
        )


def test_events_are_append_only_and_ordered(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-EVT00000001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    registry = DevJobRegistryService(tmp_path)

    first = registry.append_event(
        job_id=job_id, event_type="execution_warning",
        summary="first", actor_id=WORKER_ID, actor_role=ACTOR_ROLE,
    )
    second = registry.append_event(
        job_id=job_id, event_type="execution_blocked",
        summary="second", actor_id=WORKER_ID, actor_role=ACTOR_ROLE,
    )

    events = registry.list_events(job_id)
    assert len(events) == 2
    ids = [e["event_id"] for e in events]
    assert first["event_id"] in ids
    assert second["event_id"] in ids
    # Ordered by recorded_at ascending (append order preserved).
    assert events[0]["recorded_at"] <= events[1]["recorded_at"]


# ---------------------------------------------------------------------------
# 8. Governance boundaries preserved
# ---------------------------------------------------------------------------

def test_devworker_still_cannot_complete_after_warnings(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-GOV00000001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        evidence_package_ids=["EVPKG-MISSINGGOV01"],
    )
    svc = _make_service(tmp_path)
    svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )

    registry = DevJobRegistryService(tmp_path)
    with pytest.raises(ValueError, match="devjob_transition_requires_reviewer_or_greg"):
        registry.transition_job(job_id, "reviewed", actor_id=WORKER_ID, actor_role=ACTOR_ROLE)


def test_append_event_does_not_change_job_status(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-GOV00000002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id)
    registry = DevJobRegistryService(tmp_path)

    before = registry.get_job(job_id).status
    registry.append_event(
        job_id=job_id, event_type="execution_warning",
        summary="noise", actor_id=WORKER_ID, actor_role=ACTOR_ROLE,
    )
    after = registry.get_job(job_id).status
    assert before == after == "assigned"
