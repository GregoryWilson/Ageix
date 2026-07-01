from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.agent_role import AgentRole
from models.devjob import DevJob
from services.devjob_registry_service import DevJobRegistryService
from services.devworker_execution_service import (
    DevWorkerContext,
    DevWorkerExecutionService,
)

WORKER_ID = "claude.code-devworker-1"
ACTOR_ROLE = AgentRole.CLAUDE_CODE


def _diff_for(path: str, *, added: bool = False) -> str:
    """Build a minimal but well-formed unified diff touching a single path."""
    if added:
        return (
            f"diff --git a/{path} b/{path}\n"
            f"new file mode 100644\n"
            f"index 0000000..def5678\n"
            f"--- /dev/null\n"
            f"+++ b/{path}\n"
            f"@@ -0,0 +1 @@\n"
            f"+new content\n"
        )
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index abc1234..def5678 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,2 +1,2 @@\n"
        f" def hello():\n"
        f"-    pass\n"
        f"+    return 'x'\n"
    )


def _rename_diff(old: str, new: str) -> str:
    return (
        f"diff --git a/{old} b/{new}\n"
        f"similarity index 100%\n"
        f"rename from {old}\n"
        f"rename to {new}\n"
    )


def _multi_diff(*paths: str) -> str:
    return "".join(_diff_for(p) for p in paths)


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
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )


def _make_assigned_job(
    tmp_path: Path,
    *,
    work_context_id: str,
    allowed_paths: list[str] | None = None,
    prohibited_paths: list[str] | None = None,
) -> str:
    registry = DevJobRegistryService(tmp_path)
    job = registry.create_job(
        title="Test DevJob",
        objective="Implement feature.",
        acceptance_criteria=["Tests pass."],
        allowed_paths=allowed_paths if allowed_paths is not None else ["src/"],
        # Default to a non-empty prohibited_paths so the DevJob satisfies the
        # assignment invariant; explicit overrides (including []) are preserved.
        prohibited_paths=prohibited_paths if prohibited_paths is not None else ["secrets/"],
        work_context_id=work_context_id,
        created_by="greg",
        status="assigned",
        assigned_to=WORKER_ID,
    )
    return job.job_id


def _service(tmp_path: Path, diff: str) -> DevWorkerExecutionService:
    svc = DevWorkerExecutionService(tmp_path)
    svc._git = _MockGit(diff)
    return svc


def _no_patch_created(tmp_path: Path) -> bool:
    patches_index = tmp_path / ".ageix" / "patches" / "index.json"
    if not patches_index.exists():
        return True
    return json.loads(patches_index.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# extract_diff_paths unit behavior
# ---------------------------------------------------------------------------

def test_extract_diff_paths_modified(tmp_path: Path) -> None:
    svc = DevWorkerExecutionService(tmp_path)
    assert svc.extract_diff_paths(_diff_for("src/example.py")) == ["src/example.py"]


def test_extract_diff_paths_added_handles_dev_null(tmp_path: Path) -> None:
    svc = DevWorkerExecutionService(tmp_path)
    paths = svc.extract_diff_paths(_diff_for("src/new.py", added=True))
    assert paths == ["src/new.py"]
    assert "/dev/null" not in paths


def test_extract_diff_paths_rename_returns_both_sides(tmp_path: Path) -> None:
    svc = DevWorkerExecutionService(tmp_path)
    paths = svc.extract_diff_paths(_rename_diff("src/old.py", "src/new.py"))
    assert set(paths) == {"src/old.py", "src/new.py"}


def test_extract_diff_paths_multiple_files(tmp_path: Path) -> None:
    svc = DevWorkerExecutionService(tmp_path)
    paths = svc.extract_diff_paths(_multi_diff("src/a.py", "src/b.py"))
    assert paths == ["src/a.py", "src/b.py"]


# ---------------------------------------------------------------------------
# 1. Writes outside allowed_paths but declares only an allowed path
# ---------------------------------------------------------------------------

def test_out_of_scope_actual_diff_blocks_before_patch(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000001"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id, allowed_paths=["src/"])
    # Actual diff touches config.yaml (outside src/) while the worker declares
    # only the allowed src/example.py.
    svc = _service(tmp_path, _diff_for("config.yaml"))

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )

    assert result.status == "blocked"
    assert result.error == "devworker_path_not_authorized"
    # No patch artifact and no submitted result.
    assert _no_patch_created(tmp_path)
    registry = DevJobRegistryService(tmp_path)
    assert registry.list_results(job_id) == []
    assert registry.get_job(job_id).status == "assigned"
    # The violation is surfaced through a governed DevJob event (21.1 behavior).
    events = registry.list_events(job_id)
    assert len(events) == 1
    assert events[0]["reason"] == "devworker_path_not_authorized"
    assert events[0]["metadata"]["offending_path"] == "config.yaml"


# ---------------------------------------------------------------------------
# 2. Writes to a prohibited path (even if also under allowed)
# ---------------------------------------------------------------------------

def test_prohibited_actual_diff_blocks_even_when_under_allowed(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000002"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(
        tmp_path,
        work_context_id=work_context_id,
        allowed_paths=["src/"],
        prohibited_paths=["src/secrets/"],
    )
    svc = _service(tmp_path, _diff_for("src/secrets/key.pem"))

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/secrets/key.pem"],
    )

    assert result.status == "blocked"
    assert result.error == "devworker_path_prohibited"
    assert _no_patch_created(tmp_path)
    assert DevJobRegistryService(tmp_path).list_results(job_id) == []


# ---------------------------------------------------------------------------
# 3. Declared changed_files omits an actual changed path -> block
# ---------------------------------------------------------------------------

def test_declared_omits_actual_path_blocks_mismatch(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000003"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id, allowed_paths=["src/"])
    # Both paths are in-scope, but the worker only declares one of them.
    svc = _service(tmp_path, _multi_diff("src/a.py", "src/b.py"))

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/a.py"],
    )

    assert result.status == "blocked"
    assert result.error == "devworker_changed_files_mismatch"
    assert _no_patch_created(tmp_path)
    registry = DevJobRegistryService(tmp_path)
    assert registry.list_results(job_id) == []
    events = registry.list_events(job_id)
    assert events[0]["metadata"]["omitted_paths"] == ["src/b.py"]


# ---------------------------------------------------------------------------
# 4. Declared includes an extra path not in diff -> warning, still succeeds
# ---------------------------------------------------------------------------

def test_declared_extra_path_warns_but_succeeds(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000004"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id, allowed_paths=["src/"])
    svc = _service(tmp_path, _diff_for("src/a.py"))

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/a.py", "src/ghost.py"],
    )

    assert result.status == "submitted"
    # Actual diff paths are authoritative for the recorded changed_files.
    assert result.changed_files == ["src/a.py"]
    codes = {w["code"] for w in result.warnings}
    assert "devworker_changed_files_extra" in codes
    # Worker-declared list retained only as metadata.
    submitted = DevJobRegistryService(tmp_path).list_results(job_id)[0]
    assert submitted["metadata"]["worker_declared_changed_files"] == ["src/a.py", "src/ghost.py"]
    assert submitted["changed_files"] == ["src/a.py"]


# ---------------------------------------------------------------------------
# 5. Actual allowed-path diff succeeds normally
# ---------------------------------------------------------------------------

def test_in_scope_diff_succeeds(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000005"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id, allowed_paths=["src/"])
    svc = _service(tmp_path, _diff_for("src/example.py"))

    result = svc.execute(
        job_id,
        worker_id=WORKER_ID,
        actor_role=ACTOR_ROLE,
        implementation_fn=lambda ctx: ["src/example.py"],
    )

    assert result.status == "submitted"
    assert result.patch_id is not None and result.patch_id.startswith("PATCH-")
    assert result.changed_files == ["src/example.py"]
    assert not _no_patch_created(tmp_path)


# ---------------------------------------------------------------------------
# 6. Empty allowed_paths documents current (implicit whole-repo) behavior
# ---------------------------------------------------------------------------

def test_empty_allowed_paths_current_behavior_permits_non_prohibited(tmp_path: Path) -> None:
    # NOTE: This test documents CURRENT scope-enforcement behavior — an empty
    # allowed_paths list is treated as implicit whole-repo scope (any
    # non-prohibited path is accepted). See the TODO in validate_path: a future
    # policy should require explicit whole-repo authorization instead of
    # implicit consent. Assignment governance forbids empty allowed_paths at
    # create time, so this is exercised directly against validate_diff_scope
    # with an open-scope DevWorkerContext rather than a governed DevJob.
    ctx = DevWorkerContext(
        job=DevJob(title="Open Scope", objective="x", status="assigned"),
        workctx={}, guidance_context={}, evidence=[],
        allowed_paths=[], prohibited_paths=["secrets/"],
    )
    svc = DevWorkerExecutionService(tmp_path)

    actual = svc.validate_diff_scope(_diff_for("anywhere/in/repo.py"), ctx)
    assert actual == ["anywhere/in/repo.py"]


def test_empty_allowed_paths_still_enforces_prohibited(tmp_path: Path) -> None:
    # Even with implicit whole-repo scope, prohibited paths remain blocked.
    ctx = DevWorkerContext(
        job=DevJob(title="Open Scope", objective="x", status="assigned"),
        workctx={}, guidance_context={}, evidence=[],
        allowed_paths=[], prohibited_paths=["secrets/"],
    )
    svc = DevWorkerExecutionService(tmp_path)

    with pytest.raises(ValueError, match="devworker_path_prohibited"):
        svc.validate_diff_scope(_diff_for("secrets/token.txt"), ctx)


# ---------------------------------------------------------------------------
# validate_diff_scope direct behavior
# ---------------------------------------------------------------------------

def test_validate_diff_scope_returns_actual_paths(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000008"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id, allowed_paths=["src/"])
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    actual = svc.validate_diff_scope(_multi_diff("src/a.py", "src/b.py"), ctx)
    assert actual == ["src/a.py", "src/b.py"]


def test_validate_diff_scope_raises_on_unauthorized(tmp_path: Path) -> None:
    work_context_id = "WORKCTX-SCOPE0000009"
    _write_workctx(tmp_path, work_context_id)
    job_id = _make_assigned_job(tmp_path, work_context_id=work_context_id, allowed_paths=["src/"])
    svc = DevWorkerExecutionService(tmp_path)
    ctx = svc.load_context(job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)

    with pytest.raises(ValueError, match="devworker_path_not_authorized"):
        svc.validate_diff_scope(_diff_for("outside/x.py"), ctx)
