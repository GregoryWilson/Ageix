from __future__ import annotations

import tempfile
from pathlib import Path
from pprint import pprint

from ageix_mcp.facade_service import MCPFacadeService
from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.mcp_context import AgeixRequestContext
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _context() -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="smoke-17-8",
        project_id="Ageix",
    )


def main() -> int:
    print("== Smoke 17.8: MCP evidence access layer ==")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        decision = _approved_intent_plan(repo)
        package = EvidenceBrokerService(repo).request_evidence(
            proposal_id=decision.proposal_id,
            requester_identity={"session_id": "smoke-17-8", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
        )
        trace = CapabilityExecutionService(repo).execute(CapabilityRequest(
            capability_id="decision.trace.create",
            session_id="chair-smoke-17-8",
            agent_id="chair",
            arguments={
                "project_id": "Ageix",
                "decision_summary": "Backlog MCP evidence access layer",
                "outcome": "backlog",
                "proposal_id": decision.proposal_id,
                "evidence_package_ids": [package.package_id],
                "reason": "Chair records trace; MCP clients may inspect but not create.",
            },
        ))
        assert trace.success, trace.error

        service = MCPFacadeService(repo)
        discovery = service.execute_tool("ageix.capabilities.list", _context(), {})
        assert discovery.success, discovery.errors
        tools = {item["tool_name"] for item in discovery.result["tools"]}
        capabilities = {item["capability_id"] for item in discovery.result["capabilities"]}
        assert "ageix.evidence.package.search" in tools
        assert "ageix.evidence.package.retrieve" in tools
        assert "ageix.decision.trace.search" in tools
        assert "ageix.decision.trace.details" in tools
        assert "ageix.decision.trace.history" in tools
        assert "ageix.decision.trace.create" not in tools
        assert "evidence.package.search" in capabilities
        assert "decision.trace.search" in capabilities
        assert "decision.trace.create" not in capabilities

        search = service.execute_tool("ageix.evidence.package.search", _context(), {"query": "MCP capability exposure"})
        details = service.execute_tool("ageix.evidence.package.details", _context(), {"package_id": package.package_id})
        retrieve = service.execute_tool("ageix.evidence.package.retrieve", _context(), {"package_id": package.package_id})
        recommend = service.execute_tool("ageix.evidence.package.recommend", _context(), {"objective": "Need MCP capability exposure evidence"})
        denied_reuse = service.execute_tool("ageix.evidence.package.reuse", _context(), {"package_id": package.package_id})
        approved_reuse = service.execute_tool("ageix.evidence.package.reuse", _context(), {
            "package_id": package.package_id,
            "proposal_id": decision.proposal_id,
            "reuse_reason": "Chair-approved smoke reuse with proposal context.",
        })
        trace_search = service.execute_tool("ageix.decision.trace.search", _context(), {"query": "MCP evidence"})
        trace_details = service.execute_tool("ageix.decision.trace.details", _context(), {"trace_id": trace.result["trace_id"]})
        trace_history = service.execute_tool("ageix.decision.trace.history", _context(), {"package_id": package.package_id})
        denied_create = service.execute_tool("ageix.decision.trace.create", _context(), {"decision_summary": "External create", "outcome": "approved"})

        assert search.success, search.errors
        assert details.success, details.errors
        assert retrieve.success, retrieve.errors
        assert recommend.success, recommend.errors
        assert denied_reuse.success is False and denied_reuse.errors == ["proposal_context_required_for_package_reuse"]
        assert approved_reuse.success, approved_reuse.errors
        assert trace_search.success, trace_search.errors
        assert trace_details.success, trace_details.errors
        assert trace_history.success, trace_history.errors
        assert denied_create.success is False and denied_create.errors == ["mcp_tool_disabled"]
        assert "content" not in details.result["evidence_manifest"][0]
        assert retrieve.result["primary_evidence"][0]["content"]
        assert trace_history.result["trace_count"] == 1

        pprint({
            "package_id": package.package_id,
            "trace_id": trace.result["trace_id"],
            "search_returned": search.result["pagination"]["returned"],
            "recommendation_count": len(recommend.result["recommended_packages"]),
            "reuse_child_package_id": approved_reuse.result["package_id"],
            "chair_create_exposed": "ageix.decision.trace.create" in tools,
            "chair_create_capability_advertised": "decision.trace.create" in capabilities,
        })
    print("Smoke 17.8 PASS: MCP evidence discovery, external capability advertisement, summary-first retrieval, explicit package retrieval, governed reuse, and read-only decision trace access validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
