"""
Smoke test: DevWorker Execution Engine (Sprint 21, Phase 3)

Demonstrates the complete governed DevWorker execution flow:
  Assigned DEVJOB → Load DevJob → Verify assignment → Load WORKCTX
  → Load Guidance Context → Load referenced Evidence
  → Load authorized repository scope → Perform implementation
  → Generate real git diff → Generate governed Patch Artifact
  → Submit DevJob Result References → Stop

Then verifies that governance boundaries are preserved:
  DevWorker cannot complete, approve, or review the DevJob.
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
from services.devjob_lifecycle_service import authorize_transition
from services.devjob_registry_service import DevJobRegistryService
from services.devworker_execution_service import DevWorkerExecutionService

WORKER_ID = "claude.code-smoke-devworker"
ACTOR_ROLE = AgentRole.CLAUDE_CODE


def _git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git"] + cmd, cwd=cwd, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    print("== Smoke: DevWorker Execution Engine (Sprint 21, Phase 3) ==")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        # ----------------------------------------------------------------
        # Set up a minimal git repository for diff generation
        # ----------------------------------------------------------------
        _git(["init"], repo)
        _git(["config", "user.email", "smoke@ageix.test"], repo)
        _git(["config", "user.name", "Ageix Smoke Test"], repo)

        src_dir = repo / "src"
        src_dir.mkdir()
        (src_dir / "example.py").write_text("def hello():\n    pass\n", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "initial: add example.py"], repo)

        # ----------------------------------------------------------------
        # Persist a minimal WORKCTX package
        # ----------------------------------------------------------------
        work_context_id = "WORKCTX-SMOKE0000001"
        workctx_dir = (
            repo / ".ageix" / "architecture" / "work_context" / work_context_id
        )
        workctx_dir.mkdir(parents=True)
        (workctx_dir / "package.json").write_text(
            json.dumps({
                "work_context_id": work_context_id,
                "project_id": "Ageix",
                "work_summary": "Smoke: implement greeting function",
                "guidance_context": {
                    "summary_first": True,
                    "package_count": 0,
                    "packages": [],
                },
                "governing_principles": [
                    {"principle_id": "ARCH-PRIN-001", "title": "Governance First"},
                ],
                "active_intent": [],
                "related_adrs": [],
            }),
            encoding="utf-8",
        )
        print(f"Persisted WORKCTX: {work_context_id}")

        # ----------------------------------------------------------------
        # Persist a minimal evidence package
        # ----------------------------------------------------------------
        evpkg_id = "EVPKG-SMOKE00000001"
        evpkg_dir = repo / ".ageix" / "evidence_packages" / evpkg_id
        evpkg_dir.mkdir(parents=True)
        (evpkg_dir / "package.json").write_text(
            json.dumps({
                "package_id": evpkg_id,
                "objective": "Understand current hello() implementation",
                "primary_evidence": [
                    {
                        "path": "src/example.py",
                        "content": "def hello():\n    pass\n",
                        "classification": "primary",
                    }
                ],
                "supporting_evidence": [],
                "validation_evidence": [],
            }),
            encoding="utf-8",
        )
        print(f"Persisted evidence package: {evpkg_id}")

        # ----------------------------------------------------------------
        # Create a DevJob in assigned state
        # ----------------------------------------------------------------
        registry = DevJobRegistryService(repo)
        job = registry.create_job(
            title="Smoke: Implement greeting function",
            objective="Update example.py so hello() returns 'Hello, World!'",
            instructions=["Change the body of hello() to return the greeting string."],
            acceptance_criteria=["hello() returns 'Hello, World!'"],
            allowed_paths=["src/"],
            prohibited_paths=[],
            work_context_id=work_context_id,
            evidence_package_ids=[evpkg_id],
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )
        print(f"Created DevJob {job.job_id} (status={job.status}, assigned_to={job.assigned_to})")

        # ----------------------------------------------------------------
        # Initialize the DevWorker execution engine
        # ----------------------------------------------------------------
        engine = DevWorkerExecutionService(repo)

        # Steps 1-6: Load context
        ctx = engine.load_context(job.job_id, worker_id=WORKER_ID, actor_role=ACTOR_ROLE)
        print(
            f"Loaded context: job={ctx.job.job_id}, "
            f"workctx={ctx.workctx['work_context_id']}, "
            f"evidence={len(ctx.evidence)}, "
            f"allowed_paths={ctx.allowed_paths}, "
            f"governing_principles={len(ctx.workctx.get('governing_principles', []))}"
        )
        assert ctx.job.job_id == job.job_id
        assert ctx.workctx["work_context_id"] == work_context_id
        assert len(ctx.evidence) == 1
        assert ctx.evidence[0]["package_id"] == evpkg_id

        # Step 7: Perform implementation within authorized paths
        engine.validate_path("src/example.py", ctx)  # enforces scope
        (repo / "src" / "example.py").write_text(
            "def hello():\n    return 'Hello, World!'\n",
            encoding="utf-8",
        )
        changed_files = ["src/example.py"]
        print("Performed implementation: updated src/example.py")

        # Step 8: Generate real git diff
        diff_content = engine.generate_diff()
        assert diff_content.strip(), "Expected non-empty diff after implementation"
        assert "Hello, World!" in diff_content
        print(f"Generated diff ({len(diff_content)} bytes): OK")

        # Step 9: Generate governed Patch Artifact
        patch = engine.create_patch_artifact(diff_content, ctx)
        assert patch["patch_id"].startswith("PATCH-")
        assert patch.get("artifact_id") is not None
        patch_file = repo / ".ageix" / "patches" / patch["patch_id"] / "patch.diff"
        assert patch_file.exists()
        print(f"Created governed patch artifact: {patch['patch_id']}")

        # Step 10: Submit DevJob Result References
        outcome = engine.submit_result(
            ctx,
            patch["patch_id"],
            worker_id=WORKER_ID,
            actor_role=ACTOR_ROLE,
            changed_files=changed_files,
            artifact_ids=[str(patch.get("artifact_id", ""))],
            result_summary="Smoke: Implemented greeting function per DevJob objective.",
        )
        assert outcome["job"]["status"] == "submitted"
        result_id = outcome["result"]["result_id"]
        print(
            f"Submitted result {result_id}: "
            f"job status={outcome['job']['status']}, "
            f"patch_id={outcome['result']['patch_id']}"
        )

        # ----------------------------------------------------------------
        # Verify governance boundaries: DevWorker cannot complete or approve
        # ----------------------------------------------------------------
        final_job = registry.get_job(job.job_id)

        try:
            authorize_transition(
                final_job, "completed", actor_id=WORKER_ID, actor_role=ACTOR_ROLE,
            )
            assert False, "Should have raised — DevWorker cannot complete the job"
        except ValueError as exc:
            assert "devjob_transition_requires_greg_or_governance" in str(exc)
        print("Governance check PASS: DevWorker cannot complete the job")

        try:
            authorize_transition(
                final_job, "reviewed", actor_id=WORKER_ID, actor_role=ACTOR_ROLE,
            )
            assert False, "Should have raised — DevWorker cannot mark job reviewed"
        except ValueError as exc:
            assert "devjob_transition_requires_reviewer_or_greg" in str(exc)
        print("Governance check PASS: DevWorker cannot mark the job reviewed")

        # ----------------------------------------------------------------
        # Verify lifecycle history integrity
        # ----------------------------------------------------------------
        history_statuses = [h["to_status"] for h in final_job.lifecycle_history]
        assert "in_progress" in history_statuses, f"Expected in_progress in {history_statuses}"
        assert "submitted" in history_statuses, f"Expected submitted in {history_statuses}"
        print(f"Lifecycle history: {history_statuses}")

        # Clean up
        registry.delete_job(job.job_id)
        print(f"Cleaned up DevJob {job.job_id}")

    print()
    print("Smoke PASS: Complete governed DevWorker execution flow verified.")
    print("  — DevJob loaded and assignment verified")
    print("  — WORKCTX and Guidance Context loaded")
    print("  — Evidence Packages loaded")
    print("  — Repository scope enforced")
    print("  — Implementation performed within authorized paths")
    print("  — Real git diff generated")
    print("  — Governed Patch Artifact created")
    print("  — DevJob Result References submitted")
    print("  — Governance boundaries preserved")


if __name__ == "__main__":
    main()
