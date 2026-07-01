"""
Smoke test: DevWorker Execution Audit Hardening (Sprint 21.1)

Demonstrates that governed DevWorker execution never degrades silently.

Runs the full execute() flow against a real git repository with a DevJob that
references one present and one MISSING evidence package, then clearly shows:

  - loaded evidence package IDs
  - missing evidence package IDs
  - structured warnings
  - patch ID
  - submitted DevJob result references (with warnings + metadata)

Then runs a blocked execution (no diff) and shows the append-only DevJob event
that surfaces the blocked condition through governed DevJob state.
"""
from __future__ import annotations

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
    result = subprocess.run(
        ["git"] + cmd, cwd=cwd, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _write_workctx(repo: Path, work_context_id: str) -> None:
    workctx_dir = repo / ".ageix" / "architecture" / "work_context" / work_context_id
    workctx_dir.mkdir(parents=True)
    (workctx_dir / "package.json").write_text(
        json.dumps({
            "work_context_id": work_context_id,
            "project_id": "Ageix",
            "work_summary": "Smoke: audit-hardened execution",
            "guidance_context": {"summary_first": True, "packages": []},
        }),
        encoding="utf-8",
    )


def _write_evidence(repo: Path, package_id: str) -> None:
    evpkg_dir = repo / ".ageix" / "evidence_packages" / package_id
    evpkg_dir.mkdir(parents=True)
    (evpkg_dir / "package.json").write_text(
        json.dumps({
            "package_id": package_id,
            "objective": "Present evidence for audit smoke",
            "primary_evidence": [],
        }),
        encoding="utf-8",
    )


def main() -> None:
    print("== Smoke: DevWorker Execution Audit Hardening (Sprint 21.1) ==")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        # --- Real git repository -----------------------------------------
        _git(["init"], repo)
        _git(["config", "user.email", "smoke@ageix.test"], repo)
        _git(["config", "user.name", "Ageix Smoke Test"], repo)
        (repo / "src").mkdir()
        (repo / "src" / "example.py").write_text("def hello():\n    pass\n", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "initial"], repo)

        # --- Governed context --------------------------------------------
        work_context_id = "WORKCTX-AUDIT0000001"
        present_evpkg = "EVPKG-PRESENT000001"
        missing_evpkg = "EVPKG-MISSING000001"
        _write_workctx(repo, work_context_id)
        _write_evidence(repo, present_evpkg)  # missing_evpkg intentionally not written
        print(f"Persisted WORKCTX: {work_context_id}")
        print(f"Persisted evidence package: {present_evpkg}")
        print(f"Intentionally MISSING evidence package: {missing_evpkg}")

        registry = DevJobRegistryService(repo)
        job = registry.create_job(
            title="Smoke: audit-hardened greeting",
            objective="Update example.py so hello() returns 'Hello, World!'",
            allowed_paths=["src/"],
            work_context_id=work_context_id,
            evidence_package_ids=[present_evpkg, missing_evpkg],
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )
        print(f"Created DevJob {job.job_id} (status={job.status})")

        engine = DevWorkerExecutionService(repo)

        # --- Full governed execution with a real implementation ----------
        def implementation(ctx) -> list[str]:
            engine.validate_path("src/example.py", ctx)
            (repo / "src" / "example.py").write_text(
                "def hello():\n    return 'Hello, World!'\n", encoding="utf-8",
            )
            return ["src/example.py"]

        result = engine.execute(
            job.job_id,
            worker_id=WORKER_ID,
            actor_role=ACTOR_ROLE,
            implementation_fn=implementation,
        )

        summary = result.to_summary()
        print()
        print("--- Execution Summary (audit surface) ---")
        print(f"  status                        : {summary['status']}")
        print(f"  worker_id                     : {summary['worker_id']}")
        print(f"  job_id                        : {summary['job_id']}")
        print(f"  work_context_id               : {summary['work_context_id']}")
        print(f"  loaded_evidence_package_ids   : {summary['loaded_evidence_package_ids']}")
        print(f"  missing_evidence_package_ids  : {summary['missing_evidence_package_ids']}")
        print(f"  changed_files                 : {summary['changed_files']}")
        print(f"  patch_id                      : {summary['patch_id']}")
        print(f"  blocked_reason                : {summary['blocked_reason']}")
        print(f"  warnings                      : {len(summary['warnings'])}")
        for w in summary["warnings"]:
            print(f"    - [{w['severity']}] {w['code']}: {w['message']}")

        assert summary["status"] == "submitted"
        assert summary["loaded_evidence_package_ids"] == [present_evpkg]
        assert summary["missing_evidence_package_ids"] == [missing_evpkg]
        assert summary["patch_id"] is not None
        assert len(summary["warnings"]) == 1

        # --- Submitted DevJob result references carry the audit trail ----
        submitted = registry.list_results(job.job_id)[0]
        print()
        print("--- Submitted DevJob Result References ---")
        print(f"  result_id     : {submitted['result_id']}")
        print(f"  patch_id      : {submitted['patch_id']}")
        print(f"  changed_files : {submitted['changed_files']}")
        print(f"  metadata.missing_evidence_package_ids : {submitted['metadata']['missing_evidence_package_ids']}")
        print(f"  warnings on result                    : {len(submitted['warnings'])}")
        assert submitted["patch_id"] == summary["patch_id"]
        assert submitted["metadata"]["missing_evidence_package_ids"] == [missing_evpkg]
        assert len(submitted["warnings"]) == 1
        print("Result references PASS: warnings + missing evidence surfaced on submitted result")

        # --- Blocked execution surfaces via append-only DevJob event -----
        # Restore the working tree so the next run genuinely produces no diff.
        # (The prior change is already captured as a governed patch artifact.)
        _git(["checkout", "--", "src/example.py"], repo)

        blocked_job = registry.create_job(
            title="Smoke: blocked execution",
            objective="No-op that produces no diff",
            allowed_paths=["src/"],
            work_context_id=work_context_id,
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )
        blocked_result = engine.execute(
            blocked_job.job_id,
            worker_id=WORKER_ID,
            actor_role=ACTOR_ROLE,
            implementation_fn=lambda ctx: [],  # makes no change → empty diff
        )
        print()
        print("--- Blocked Execution ---")
        print(f"  status         : {blocked_result.status}")
        print(f"  blocked_reason : {blocked_result.error}")
        assert blocked_result.status == "blocked"
        assert blocked_result.error == "devworker_no_changes_detected"

        events = registry.list_events(blocked_job.job_id)
        assert len(events) == 1
        event = events[0]
        print(f"  DevJob event   : {event['event_type']} (reason={event['reason']})")
        print(f"  event warnings : {len(event['warnings'])}")
        assert event["event_type"] == "execution_blocked"
        # Blocked execution must NOT advance the DevJob or submit a result.
        assert registry.get_job(blocked_job.job_id).status == "assigned"
        assert registry.list_results(blocked_job.job_id) == []
        print("Blocked execution PASS: surfaced via append-only DevJob event; lifecycle unchanged")

        # --- Governance boundaries still hold ----------------------------
        try:
            registry.transition_job(job.job_id, "reviewed", actor_id=WORKER_ID, actor_role=ACTOR_ROLE)
            assert False, "DevWorker must not be able to review its own work"
        except ValueError as exc:
            assert "devjob_transition_requires_reviewer_or_greg" in str(exc)
        print("Governance check PASS: DevWorker cannot review the job")

        registry.delete_job(job.job_id)
        registry.delete_job(blocked_job.job_id)

    print()
    print("Smoke PASS: DevWorker execution is audit-friendly end-to-end.")
    print("  — loaded and missing evidence both surfaced (no silent skip)")
    print("  — structured warnings captured in the execution summary")
    print("  — warnings + missing evidence attached to submitted result references")
    print("  — blocked execution surfaced via append-only DevJob event")
    print("  — governance boundaries preserved")


if __name__ == "__main__":
    main()
