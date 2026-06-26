from __future__ import annotations

import tempfile
from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        print("== Smoke 17.7: historical evidence and decision traceability ==")
        decision = _approved_intent_plan(repo)
        package = EvidenceBrokerService(repo).request_evidence(
            proposal_id=decision.proposal_id,
            requester_identity={"session_id": "smoke-17-7", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
        )
        execution = CapabilityExecutionService(repo)

        created = execution.execute(CapabilityRequest(
            capability_id="decision.trace.create",
            session_id="smoke-17-7",
            agent_id="lex",
            arguments={
                "project_id": "Ageix",
                "client_id": "chatgpt",
                "decision_summary": "Approve package-backed MCP evidence traceability smoke decision.",
                "outcome": "approved",
                "proposal_id": decision.proposal_id,
                "evidence_package_ids": [package.package_id],
                "reason": "Chair approved historical trace creation during Sprint 17.7 smoke.",
                "outcome_metadata": {"backlog_id": None, "deferred_until": None},
            },
        ))
        assert created.success, created.error
        pprint({"created_trace": created.result["trace_id"], "package_id": package.package_id})

        # Drift the repo after the historical trace to prove current freshness can be reported
        # without rewriting immutable package contents.
        changed_path = package.primary_evidence[0].path
        with open(repo / changed_path, "a", encoding="utf-8") as handle:
            handle.write("\n# smoke 17.7 drift\n")

        retrieved = execution.execute(CapabilityRequest(
            capability_id="decision.trace.get",
            session_id="smoke-17-7",
            agent_id="lex",
            arguments={"project_id": "Ageix", "client_id": "chatgpt", "trace_id": created.result["trace_id"]},
        ))
        assert retrieved.success, retrieved.error
        linked = retrieved.result["evidence_packages"][0]
        assert linked["current_freshness"]["stale"] is True
        assert changed_path in linked["current_freshness"]["changed_paths"]

        history = execution.execute(CapabilityRequest(
            capability_id="decision.trace.package_history",
            session_id="smoke-17-7",
            agent_id="lex",
            arguments={"project_id": "Ageix", "client_id": "chatgpt", "package_id": package.package_id},
        ))
        assert history.success, history.error
        assert history.result["trace_count"] == 1
        pprint({"history_trace_count": history.result["trace_count"], "freshness_status": linked["current_freshness"]["status"]})
        print("Smoke 17.7 PASS: append-only decision trace, evidence links, package history, and current freshness awareness validated.")


if __name__ == "__main__":
    main()
