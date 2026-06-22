from __future__ import annotations

import tempfile
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _items(package):
    return package.primary_evidence + package.supporting_evidence + package.validation_evidence


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        decision = _approved_intent_plan(repo)
        package = EvidenceBrokerService(repo).request_evidence(
            proposal_id=decision.proposal_id,
            requester_identity={"session_id": "smoke-17-3", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
        )
        execution = CapabilityExecutionService(repo)

        listed = execution.execute(CapabilityRequest(
            capability_id="evidence.package.list",
            session_id="smoke-17-3",
            agent_id="lex",
            arguments={"project_id": "Ageix", "limit": 10, "context_contains": package.package_id[-6:]},
        ))
        assert listed.success, listed.error
        assert listed.result["packages"][0]["package_id"] == package.package_id

        details = execution.execute(CapabilityRequest(
            capability_id="evidence.package.details",
            session_id="smoke-17-3",
            agent_id="lex",
            arguments={"project_id": "Ageix", "package_id": package.package_id},
        ))
        assert details.success, details.error
        assert details.result["evidence_manifest"]
        assert "content" not in details.result["evidence_manifest"][0]

        changed_path = _items(package)[0].path
        with open(repo / changed_path, "a", encoding="utf-8") as handle:
            handle.write("\n# smoke 17.3 drift\n")
        freshness = execution.execute(CapabilityRequest(
            capability_id="evidence.package.freshness",
            session_id="smoke-17-3",
            agent_id="lex",
            arguments={"project_id": "Ageix", "package_id": package.package_id},
        ))
        assert freshness.success, freshness.error
        assert freshness.result["stale"] is True
        assert changed_path in freshness.result["changed_paths"]

        rehydrated = execution.execute(CapabilityRequest(
            capability_id="evidence.package.rehydrate",
            session_id="smoke-17-3",
            agent_id="lex",
            arguments={"project_id": "Ageix", "package_id": package.package_id},
        ))
        assert rehydrated.success, rehydrated.error
        assert rehydrated.metadata["freshness_evaluated"] is False
        assert rehydrated.result["package_id"] == package.package_id

        print(
            "Smoke 17.3 PASS: package discovery, summaries, details, freshness, "
            f"and immutable rehydration verified for {package.package_id}."
        )


if __name__ == "__main__":
    main()
