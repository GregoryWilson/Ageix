from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from models.agent_role import AgentRole
from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.devjob_registry_service import DevJobRegistryService


def main() -> None:
    print("== Smoke: DevJob coordination primitive (INTENT-0007) ==")
    with TemporaryDirectory() as tmp:
        repo = Path(tmp)
        execution = CapabilityExecutionService(repo)

        # 1. Create a temporary DevJob.
        created = execution.execute(CapabilityRequest(
            capability_id="devjob.create",
            session_id="smoke-devjob",
            agent_id="claude.ai",
            arguments={
                "client_id": "ageix-connector-claude-ai",
                "agent_role": "claude.ai",
                "title": "Smoke DevJob",
                "objective": "Exercise the DevJob coordination primitive end-to-end.",
                "status": "assigned",
                "assigned_to": "ageix-connector-claude-code",
                "created_by": "greg",
            },
        ))
        assert created.success, created.error
        job_id = created.result["job_id"]
        print(f"Created DevJob {job_id} with status={created.result['status']}")

        # 2. Retrieve it.
        fetched = execution.execute(CapabilityRequest(
            capability_id="devjob.get",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={"client_id": "ageix-connector-claude-code", "job_id": job_id},
        ))
        assert fetched.success, fetched.error
        assert fetched.result["job_id"] == job_id
        print(f"Retrieved DevJob {job_id}: {fetched.result['title']!r}")

        # in_progress is not yet its own MCP capability in this sprint; move the
        # job there at the service layer so result.submit's transition is valid.
        DevJobRegistryService(repo).transition_job(
            job_id, "in_progress", actor_id="ageix-connector-claude-code", actor_role=AgentRole.CLAUDE_CODE,
        )

        # 3. Submit a temporary result.
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

        # 4. Verify lifecycle state.
        verified = execution.execute(CapabilityRequest(
            capability_id="devjob.get",
            session_id="smoke-devjob",
            agent_id="claude.code",
            arguments={"client_id": "ageix-connector-claude-code", "job_id": job_id},
        ))
        assert verified.success, verified.error
        assert verified.result["status"] == "submitted"
        history_statuses = [entry["to_status"] for entry in verified.result["lifecycle_history"]]
        assert history_statuses == ["assigned", "in_progress", "submitted"]
        print(f"Verified DevJob {job_id} lifecycle: {history_statuses}")

        # 5. Briefly pause.
        time.sleep(1)

        # 6. Clean up the smoke DevJob and index entry.
        registry = DevJobRegistryService(repo)
        registry.delete_job(job_id)
        index_ids = {item["job_id"] for item in registry._read_index()}
        assert job_id not in index_ids
        assert not (repo / ".ageix" / "devjobs" / job_id).exists()
        print(f"Cleaned up DevJob {job_id} and its index entry.")

    print("Smoke PASS: DevJob created, retrieved, result submitted, lifecycle verified, and cleaned up.")


if __name__ == "__main__":
    main()
