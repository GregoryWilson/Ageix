from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.devjob_registry_service import DevJobRegistryService

WORK_CONTEXT_ID = "WORKCTX-SMOKE00000001"


def _seed_work_context(repo: Path) -> None:
    """Fabricates a minimal WORKCTX-* package; assignment only validates existence."""
    package_dir = repo / ".ageix" / "architecture" / "work_context" / WORK_CONTEXT_ID
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "package.json").write_text(
        json.dumps({"work_context_id": WORK_CONTEXT_ID, "created_by": "greg"}), encoding="utf-8",
    )


def main() -> None:
    print("== Smoke: DevJob coordination primitive (INTENT-0007 Phase 2) ==")
    with TemporaryDirectory() as tmp:
        repo = Path(tmp)
        execution = CapabilityExecutionService(repo)
        _seed_work_context(repo)

        # 1. Create a temporary draft DevJob.
        created = execution.execute(CapabilityRequest(
            capability_id="devjob.create",
            session_id="smoke-devjob",
            agent_id="claude.ai",
            arguments={
                "client_id": "ageix-connector-claude-ai",
                "agent_role": "claude.ai",
                "title": "Smoke DevJob",
                "objective": "Exercise the DevJob coordination primitive end-to-end.",
                "created_by": "greg",
            },
        ))
        assert created.success, created.error
        job_id = created.result["job_id"]
        assert created.result["status"] == "draft"
        print(f"Created draft DevJob {job_id}.")

        # 2. Assignment without a Work Context must be denied.
        denied = execution.execute(CapabilityRequest(
            capability_id="devjob.assign",
            session_id="smoke-devjob",
            agent_id="greg",
            arguments={
                "client_id": "greg",
                "actor_id": "greg",
                "job_id": job_id,
                "assigned_to": "ageix-connector-claude-code",
                "acceptance_criteria": ["Smoke criteria"],
                "allowed_paths": ["scripts/"],
                "prohibited_paths": ["secrets/"],
            },
        ))
        assert not denied.success and denied.error == "devjob_assignment_requires_work_context"
        print("Confirmed assignment without Work Context is denied.")

        # 3. Assign with a valid Work Context.
        assigned = execution.execute(CapabilityRequest(
            capability_id="devjob.assign",
            session_id="smoke-devjob",
            agent_id="greg",
            arguments={
                "client_id": "greg",
                "actor_id": "greg",
                "job_id": job_id,
                "work_context_id": WORK_CONTEXT_ID,
                "acceptance_criteria": ["Smoke criteria"],
                "allowed_paths": ["scripts/"],
                "prohibited_paths": ["secrets/"],
                "assigned_to": "ageix-connector-claude-code",
            },
        ))
        assert assigned.success, assigned.error
        assert assigned.result["status"] == "assigned"
        print(f"Assigned DevJob {job_id} with status={assigned.result['status']}")

        # 4. Retrieve it.
        fetched = execution.execute(CapabilityRequest(
            capability_id="devjob.get",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={"client_id": "ageix-connector-claude-code", "job_id": job_id},
        ))
        assert fetched.success, fetched.error
        assert fetched.result["job_id"] == job_id
        print(f"Retrieved DevJob {job_id}: {fetched.result['title']!r}")

        # 5. Move it to in_progress via the devjob.transition capability.
        started = execution.execute(CapabilityRequest(
            capability_id="devjob.transition",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={
                "client_id": "ageix-connector-claude-code",
                "agent_role": "claude.code",
                "actor_id": "ageix-connector-claude-code",
                "job_id": job_id,
                "target_status": "in_progress",
            },
        ))
        assert started.success, started.error
        print(f"Moved DevJob {job_id} to in_progress.")

        # 6. Attach a git synchronization reference, by reference only.
        synced = execution.execute(CapabilityRequest(
            capability_id="devjob.sync.attach",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={
                "client_id": "ageix-connector-claude-code",
                "agent_role": "claude.code",
                "actor_id": "ageix-connector-claude-code",
                "job_id": job_id,
                "branch": "feature/smoke-devjob",
            },
        ))
        assert synced.success, synced.error
        print("Attached git sync reference.")

        # 7. Submit a temporary result.
        submitted = execution.execute(CapabilityRequest(
            capability_id="devjob.result.submit",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={
                "client_id": "ageix-connector-claude-code",
                "agent_role": "claude.code",
                "actor_id": "ageix-connector-claude-code",
                "job_id": job_id,
                "result_summary": "Smoke result submission.",
                "patch_id": "PATCH-SMOKE00000000",
                "validation_run_id": "VALRUN-SMOKE0000000",
            },
        ))
        assert submitted.success, submitted.error
        print(f"Submitted result {submitted.result['result']['result_id']} for DevJob {job_id}")

        # 8. Submit a review decision.
        reviewed = execution.execute(CapabilityRequest(
            capability_id="devjob.review.submit",
            session_id="smoke-devjob",
            agent_id="greg",
            arguments={"client_id": "greg", "actor_id": "greg", "job_id": job_id, "decision": "approved"},
        ))
        assert reviewed.success, reviewed.error
        assert reviewed.result["status"] == "reviewed"
        print(f"Reviewed DevJob {job_id}.")

        # 9. Completion must fail without review/validation/sync all satisfied — confirm it now succeeds.
        completed = execution.execute(CapabilityRequest(
            capability_id="devjob.transition",
            session_id="smoke-devjob",
            agent_id="greg",
            arguments={"client_id": "greg", "actor_id": "greg", "job_id": job_id, "target_status": "completed"},
        ))
        assert completed.success, completed.error
        assert completed.result["status"] == "completed"
        print(f"Completed DevJob {job_id}.")

        # 10. Verify the full governed event history.
        events = execution.execute(CapabilityRequest(
            capability_id="devjob.event.list",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={"client_id": "ageix-connector-claude-code", "job_id": job_id},
        ))
        assert events.success, events.error
        event_types = {event["event_type"] for event in events.result["events"]}
        assert {"lifecycle_transition", "git_sync_attached", "review_submitted"} <= event_types
        print(f"Verified DevJob {job_id} governed event history: {sorted(event_types)}")

        # 11. Briefly pause.
        time.sleep(1)

        # 12. Clean up the smoke DevJob and index entry.
        registry = DevJobRegistryService(repo)
        registry.delete_job(job_id)
        index_ids = {item["job_id"] for item in registry._read_index()}
        assert job_id not in index_ids
        assert not (repo / ".ageix" / "devjobs" / job_id).exists()
        print(f"Cleaned up DevJob {job_id} and its index entry.")

    print("Smoke PASS: DevJob created, assignment governance enforced, lifecycle hardened, and cleaned up.")


if __name__ == "__main__":
    main()
