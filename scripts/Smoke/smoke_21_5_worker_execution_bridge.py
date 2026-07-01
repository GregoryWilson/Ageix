"""
Smoke test: Worker Execution Bridge (Sprint 21.5)

Demonstrates the complete governed chain no longer terminating at
"directive recorded":

  Chair Intent -> Delegation -> Directive -> DevJob
    -> Worker Admission -> Worker Launcher Artifact
    -> Worker Execution Bridge -> Launch Provider -> Claude Code

Shows:
  1. A delegated directive is submitted (Sprint 25.4.5.1 path).
  2. The execution bridge engages the assigned worker.
  3. With no launch provider -> a durable queued launch request; DevJob -> in_progress.
  4. With a configured launch provider -> the worker is launched automatically.
  5. Worker session references and full traceability are recorded.
  6. Invalid engagement fails cleanly.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from models.agent_role import AgentRole
from services.chair_delegation_service import ChairDelegationService
from services.conversation_directive_service import DIRECTIVE_ACTION, ConversationDirectiveService
from services.devjob_registry_service import DevJobRegistryService
from services.launch_providers.local_command import ClaudeCodeCliLaunchProvider
from services.worker_execution_bridge_service import WorkerExecutionBridgeService

GOV_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
WORKER = "claude-code-worker-1"
CONV = "CONV-21-5-SMOKE01"


def main() -> None:
    print("== Smoke: Worker Execution Bridge (Sprint 21.5) ==")

    # --- Scenario A: full chain, no provider -> durable queued request ------
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        devjobs = DevJobRegistryService(repo)
        bridge = WorkerExecutionBridgeService(repo)

        job = devjobs.create_job(
            title="Sprint 25.5 implementation", objective="Do the work.",
            created_by="greg", status="assigned", assigned_to=WORKER,
        )
        print(f"DevJob {job.job_id} assigned to {job.assigned_to} (status={job.status})")

        # Chair delegation + delegated directive (upstream governed intent).
        delegation = ChairDelegationService(repo).create_delegation(
            delegate="lex", allowed_actions=[DIRECTIVE_ACTION], actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
            reason="Authorize the Sprint 25.5 directive.",
        )
        directive = ConversationDirectiveService(repo).submit_delegated_directive(
            conversation_id=CONV, content=f"Proceed on {job.job_id}.", delegate="lex",
            delegation_id=delegation.delegation_id, speaker_client_id="ageix-connector-lex",
            speaker_agent_role=AgentRole.LEX, speaker_session_id="sess-lex", model_id="lex",
        )
        directive_turn_id = directive["turn"]["turn_id"]
        print(f"Delegated directive recorded: turn={directive_turn_id}, "
              f"delegation={delegation.delegation_id} (consumed)")

        # Execution bridge — no provider configured -> queued.
        record = bridge.engage_worker(
            devjob_id=job.job_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
            directive_turn_id=directive_turn_id, delegation_id=delegation.delegation_id,
            conversation_id=CONV, providers=[],
        )
        print()
        print("--- Worker Execution Bridge (no provider) ---")
        print(f"  state            : {record['state']}")
        print(f"  devjob status    : {record['devjob_status_after']}")
        print(f"  admission ticket : {record['admission_ticket_id']}")
        print(f"  launch artifact  : {record['launch_artifact_id']}")
        print(f"  execution record : {record['execution_id']}")
        print(f"  traceability     : directive={record['directive_turn_id']} "
              f"delegation={record['delegation_id']} governed_artifact={record['traceability']['governed_artifact_id']}")
        assert record["state"] == "worker_queued"
        assert record["devjob_status_after"] == "in_progress"
        assert devjobs.get_job(job.job_id).status == "in_progress"
        events = [e["event_type"] for e in devjobs.list_events(job.job_id)]
        assert "worker_queued" in events
        print("Queued PASS: durable queued launch request; DevJob -> in_progress; state on lifecycle")

        # Invalid re-engagement fails cleanly.
        try:
            bridge.engage_worker(devjob_id=job.job_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE, providers=[])
            raise AssertionError("re-engaging an in_progress DevJob must fail")
        except ValueError as exc:
            assert "worker_execution_devjob_not_launchable" in str(exc)
        print("Clean-failure PASS: non-launchable DevJob rejected")

    # --- Scenario B: configured provider -> worker launched automatically ---
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        devjobs = DevJobRegistryService(repo)
        bridge = WorkerExecutionBridgeService(repo)
        job = devjobs.create_job(
            title="Launch me", objective="x", created_by="greg", status="assigned", assigned_to=WORKER,
        )
        # A configured (opt-in) launch command. 'true' is harmless and proves a
        # real process is spawned and a session reference returned.
        provider = ClaudeCodeCliLaunchProvider(repo, command="true")
        record = bridge.engage_worker(
            devjob_id=job.job_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE, providers=[provider],
        )
        print()
        print("--- Worker Execution Bridge (configured provider) ---")
        print(f"  state         : {record['state']}")
        print(f"  provider      : {record['launch_provider']}")
        print(f"  session ref   : {record['worker_session_ref']}")
        print(f"  devjob status : {record['devjob_status_after']}")
        assert record["state"] == "worker_launched"
        assert record["launch_provider"] == "claude_code_cli"
        assert isinstance(record["worker_session_ref"].get("pid"), int)
        assert record["devjob_status_after"] == "in_progress"
        print("Launched PASS: configured provider launched the worker; session reference traceable")

    print()
    print("Smoke PASS: the governed chair->delegation->directive->devjob->admission->")
    print("launcher-artifact->execution-bridge->provider->worker chain is complete,")
    print("auditable, and operational. Governance never learns how the worker is launched.")


if __name__ == "__main__":
    main()
