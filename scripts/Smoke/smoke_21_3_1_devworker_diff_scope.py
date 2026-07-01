"""
Smoke test: DevWorker Diff Scope Enforcement (Sprint 21.3.1)

Demonstrates that the ACTUAL git diff — not worker-declared changed_files —
determines whether the generated patch is within authorized DevJob scope.

Shows:
  1. A valid, in-scope execution succeeds and produces a governed patch.
  2. An out-of-scope diff is blocked BEFORE any patch artifact is created,
     even when the worker declares only an allowed path.

Uses a real git repository and real diffs.
"""
from __future__ import annotations

# Allow running from the repo root without PYTHONPATH=. (mirrors other smokes).
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import json
import subprocess
import tempfile
from pathlib import Path

from models.agent_role import AgentRole
from services.devjob_registry_service import DevJobRegistryService
from services.devworker_execution_service import DevWorkerExecutionService

WORKER_ID = "claude.code-smoke-devworker"
ACTOR_ROLE = AgentRole.CLAUDE_CODE


def _git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _write_workctx(repo: Path, work_context_id: str) -> None:
    d = repo / ".ageix" / "architecture" / "work_context" / work_context_id
    d.mkdir(parents=True)
    (d / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id,
            "project_id": "Ageix",
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )


def _patch_count(repo: Path) -> int:
    idx = repo / ".ageix" / "patches" / "index.json"
    if not idx.exists():
        return 0
    return len(json.loads(idx.read_text(encoding="utf-8")))


def main() -> None:
    print("== Smoke: DevWorker Diff Scope Enforcement (Sprint 21.3.1) ==")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(["init"], repo)
        _git(["config", "user.email", "smoke@ageix.test"], repo)
        _git(["config", "user.name", "Ageix Smoke Test"], repo)
        (repo / "src").mkdir()
        (repo / "src" / "example.py").write_text("def hello():\n    pass\n", encoding="utf-8")
        # A tracked out-of-scope file, so a modification shows up in `git diff HEAD`.
        (repo / "config.yaml").write_text("key: value\n", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "initial"], repo)

        work_context_id = "WORKCTX-SCOPE-SMOKE01"
        _write_workctx(repo, work_context_id)
        registry = DevJobRegistryService(repo)
        engine = DevWorkerExecutionService(repo)

        # ---------------------------------------------------------------
        # 1. Valid, in-scope execution succeeds
        # ---------------------------------------------------------------
        good_job = registry.create_job(
            title="Smoke: in-scope change",
            objective="Update src/example.py within scope.",
            allowed_paths=["src/"],
            work_context_id=work_context_id,
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )

        def in_scope_impl(ctx) -> list[str]:
            (repo / "src" / "example.py").write_text(
                "def hello():\n    return 'Hello, World!'\n", encoding="utf-8",
            )
            return ["src/example.py"]

        good = engine.execute(
            good_job.job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE,
            implementation_fn=in_scope_impl,
        )
        print()
        print("--- Valid scoped execution ---")
        print(f"  status        : {good.status}")
        print(f"  patch_id      : {good.patch_id}")
        print(f"  changed_files : {good.changed_files}  (authoritative = actual diff)")
        assert good.status == "submitted"
        assert good.patch_id is not None
        assert good.changed_files == ["src/example.py"]
        assert _patch_count(repo) == 1
        print("Valid execution PASS: in-scope diff produced a governed patch artifact")

        # Restore tree so the next run's diff is solely the out-of-scope change.
        _git(["checkout", "--", "src/example.py"], repo)

        # ---------------------------------------------------------------
        # 2. Out-of-scope diff is blocked BEFORE patch creation
        # ---------------------------------------------------------------
        bad_job = registry.create_job(
            title="Smoke: out-of-scope change",
            objective="Attempt to modify config.yaml outside allowed scope.",
            allowed_paths=["src/"],
            work_context_id=work_context_id,
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )

        def out_of_scope_impl(ctx) -> list[str]:
            # Writes OUTSIDE allowed_paths, but declares only an allowed path.
            (repo / "config.yaml").write_text("key: tampered\n", encoding="utf-8")
            return ["src/example.py"]  # dishonest / buggy declaration

        patches_before = _patch_count(repo)
        bad = engine.execute(
            bad_job.job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE,
            implementation_fn=out_of_scope_impl,
        )
        print()
        print("--- Out-of-scope execution ---")
        print(f"  status         : {bad.status}")
        print(f"  blocked_reason : {bad.error}")
        assert bad.status == "blocked"
        assert bad.error == "devworker_path_not_authorized"

        # No patch artifact created, no result submitted, DevJob unchanged.
        assert _patch_count(repo) == patches_before, "No patch must be created for an out-of-scope diff"
        assert registry.list_results(bad_job.job_id) == []
        assert registry.get_job(bad_job.job_id).status == "assigned"

        events = registry.list_events(bad_job.job_id)
        assert len(events) == 1
        event = events[0]
        print(f"  DevJob event   : {event['event_type']} (reason={event['reason']})")
        print(f"  offending_path : {event['metadata']['offending_path']}")
        assert event["reason"] == "devworker_path_not_authorized"
        assert event["metadata"]["offending_path"] == "config.yaml"
        print("Out-of-scope PASS: blocked before patch creation; surfaced via governed DevJob event")

        registry.delete_job(good_job.job_id)
        registry.delete_job(bad_job.job_id)

    print()
    print("Smoke PASS: actual git diff paths — not worker-declared metadata —")
    print("determine whether the generated patch is within authorized DevJob scope.")


if __name__ == "__main__":
    main()
