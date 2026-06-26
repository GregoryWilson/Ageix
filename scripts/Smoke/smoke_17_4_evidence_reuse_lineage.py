from __future__ import annotations

import tempfile
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _execute(service: CapabilityExecutionService, capability_id: str, arguments: dict, *, agent_id: str = "lex"):
    return service.execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="smoke-17-4",
        agent_id=agent_id,
        arguments=arguments,
    ))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        print(f"Smoke 17.4 package store: temporary ({repo / '.ageix' / 'evidence_packages'})")
        decision = _approved_intent_plan(repo)
        parent = EvidenceBrokerService(repo).request_evidence(
            proposal_id=decision.proposal_id,
            requester_identity={"session_id": "smoke-17-4", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
        )
        service = CapabilityExecutionService(repo)

        recommendations = _execute(service, "evidence.package.recommend", {
            "project_id": "Ageix",
            "client_id": "chatgpt",
            "objective": "Need to understand MCP capability exposure",
        })
        assert recommendations.success is True
        assert recommendations.result["recommended_packages"]
        assert recommendations.result["recommended_packages"][0]["package_id"] == parent.package_id
        assert recommendations.result["governance"]["chair_authority_required"] is True

        denied = _execute(service, "evidence.package.recommend", {
            "project_id": "Ageix",
            "client_id": "gemini",
            "objective": "Need to understand MCP capability exposure",
        }, agent_id="gemini")
        assert denied.success is True
        assert denied.result["recommended_packages"] == []

        reuse = _execute(service, "evidence.package.reuse", {
            "project_id": "Ageix",
            "client_id": "chatgpt",
            "package_id": parent.package_id,
            "reuse_reason": "Chair approved reuse during Sprint 17.4 smoke.",
        })
        assert reuse.success is True
        child_id = reuse.result["package_id"]
        assert child_id != parent.package_id
        assert reuse.result["parent_package_ids"] == [parent.package_id]

        lineage = _execute(service, "evidence.package.lineage", {
            "project_id": "Ageix",
            "client_id": "chatgpt",
            "package_id": parent.package_id,
        })
        assert lineage.success is True
        assert lineage.result["children"][0]["package_id"] == child_id

        refresh = _execute(service, "evidence.package.reuse", {
            "project_id": "Ageix",
            "client_id": "chatgpt",
            "package_id": parent.package_id,
            "automatic_refresh": True,
        })
        assert refresh.success is False
        assert refresh.error == "automatic_refresh_not_allowed"

        print(
            "Smoke 17.4 PASS: visibility-filtered recommendations, immutable reuse child, lineage, and refresh denial verified "
            f"for {parent.package_id} -> {child_id}. "
            "Temporary package store is cleaned up after this smoke."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
