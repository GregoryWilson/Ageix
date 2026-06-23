from __future__ import annotations

from pathlib import Path

import pytest

from ageix_mcp.facade_service import MCPFacadeService
from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.decision_trace_service import DecisionTraceService
from services.evidence_broker_service import EvidenceBrokerService
from services.mcp_context import AgeixRequestContext
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _context() -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="thread-17-8",
        project_id="Ageix",
    )


def _package(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-8", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
    )
    return decision, package


def _chair_trace(tmp_path: Path, package_id: str, proposal_id: str):
    return CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="decision.trace.create",
        session_id="chair-17-8",
        agent_id="chair",
        arguments={
            "project_id": "Ageix",
            "decision_summary": "Backlog MCP evidence access traceability",
            "outcome": "backlog",
            "proposal_id": proposal_id,
            "evidence_package_ids": [package_id],
            "reason": "Chair records historical evidence access decision.",
        },
    ))


def test_mcp_evidence_access_tools_are_discoverable_without_chair_create(tmp_path: Path):
    names = {tool.name for tool in MCPToolRegistry().list_tools() if tool.category in {"evidence", "decision_trace"}}

    assert "ageix.evidence.package.list" in names
    assert "ageix.evidence.package.search" in names
    assert "ageix.evidence.package.details" in names
    assert "ageix.evidence.package.retrieve" in names
    assert "ageix.evidence.package.recommend" in names
    assert "ageix.evidence.package.reuse" in names
    assert "ageix.decision.trace.list" in names
    assert "ageix.decision.trace.search" in names
    assert "ageix.decision.trace.details" in names
    assert "ageix.decision.trace.history" in names
    assert "ageix.decision.trace.create" not in names


def test_mcp_summary_first_then_explicit_retrieve_returns_contents(tmp_path: Path):
    _, package = _package(tmp_path)
    service = MCPFacadeService(tmp_path)

    details = service.execute_tool("ageix.evidence.package.details", _context(), {"package_id": package.package_id})
    retrieved = service.execute_tool("ageix.evidence.package.retrieve", _context(), {"package_id": package.package_id})

    assert details.success is True
    assert details.metadata["tool_name"] == "ageix.evidence.package.details"
    assert details.metadata["contents_returned"] is False
    assert "evidence_manifest" in details.result
    assert "content" not in details.result["evidence_manifest"][0]
    assert retrieved.success is True
    assert retrieved.metadata["tool_name"] == "ageix.evidence.package.retrieve"
    assert retrieved.metadata["immutable_contents_returned"] is True
    assert retrieved.result["primary_evidence"][0]["content"]


def test_mcp_recommend_defaults_to_top_five_but_agent_can_request_limit(tmp_path: Path):
    for _ in range(7):
        _package(tmp_path)
    service = MCPFacadeService(tmp_path)

    defaulted = service.execute_tool("ageix.evidence.package.recommend", _context(), {"objective": "Need MCP capability exposure evidence"})
    limited = service.execute_tool("ageix.evidence.package.recommend", _context(), {"objective": "Need MCP capability exposure evidence", "limit": 2})

    assert defaulted.success is True
    assert len(defaulted.result["recommended_packages"]) == 5
    assert limited.success is True
    assert len(limited.result["recommended_packages"]) == 2


def test_mcp_package_reuse_requires_governance_context(tmp_path: Path):
    decision, package = _package(tmp_path)
    service = MCPFacadeService(tmp_path)

    denied = service.execute_tool("ageix.evidence.package.reuse", _context(), {"package_id": package.package_id})
    approved = service.execute_tool("ageix.evidence.package.reuse", _context(), {
        "package_id": package.package_id,
        "proposal_id": decision.proposal_id,
        "reuse_reason": "Chair approved reuse through proposal context.",
    })

    assert denied.success is False
    assert denied.errors == ["proposal_context_required_for_package_reuse"]
    assert denied.governance["chair_authority_preserved"] is True
    assert approved.success is True
    assert approved.result["parent_package_ids"] == [package.package_id]


def test_mcp_decision_trace_search_details_and_history_are_read_only(tmp_path: Path):
    decision, package = _package(tmp_path)
    created = _chair_trace(tmp_path, package.package_id, decision.proposal_id)
    assert created.success is True
    trace_id = created.result["trace_id"]
    service = MCPFacadeService(tmp_path)

    search = service.execute_tool("ageix.decision.trace.search", _context(), {"query": "MCP evidence"})
    details = service.execute_tool("ageix.decision.trace.details", _context(), {"trace_id": trace_id})
    history = service.execute_tool("ageix.decision.trace.history", _context(), {"package_id": package.package_id})
    create = service.execute_tool("ageix.decision.trace.create", _context(), {"decision_summary": "Nope", "outcome": "approved"})

    assert search.success is True
    assert search.result["traces"][0]["trace_id"] == trace_id
    assert details.success is True
    assert details.result["evidence_packages"][0]["package_id"] == package.package_id
    assert history.success is True
    assert history.result["trace_count"] == 1
    assert create.success is False
    assert create.errors == ["mcp_tool_disabled"]


def test_decision_trace_visibility_inherits_package_visibility(tmp_path: Path):
    decision, package = _package(tmp_path)
    trace = DecisionTraceService(tmp_path).create_trace(
        decision_summary="Restricted package trace",
        outcome="approved",
        requester_identity={"session_id": "chair-17-8", "agent_id": "chair", "project_id": "Ageix"},
        proposal_id=decision.proposal_id,
        evidence_package_ids=[package.package_id],
    )

    with pytest.raises(ValueError, match="evidence_package_visibility_denied"):
        DecisionTraceService(tmp_path).get_trace(
            trace.trace_id,
            requester_identity={"session_id": "thread-17-8-other", "agent_id": "other_agent", "project_id": "Ageix", "client_id": "chatgpt"},
        )
