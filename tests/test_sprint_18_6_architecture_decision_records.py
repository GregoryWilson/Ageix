from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.architecture_registry_service import ArchitectureRegistryService
from services.capability_registry_service import CapabilityRegistryService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        session_id="session-18-6",
        agent_id="lex",
        project_id=project_id,
        client_id="chatGPT",
        provider="chatGPT",
        authentication_method="dev_token",
    )


def _seed(tmp_path: Path) -> str:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project", description="Project root.")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Architecture domain.")
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="ADR Governance", node_key="ADRGovernance", parent_id=domain.architecture_id, node_type="component", description="Architecture decision record governance component.")
    return component.architecture_id


def _propose(tmp_path: Path, architecture_id: str, title: str = "Capture architecture decisions"):
    return ArchitectureDecisionRecordService(tmp_path).propose_adr(
        project_id="Ageix_Test",
        session_id="session-18-6",
        created_by="lex",
        title=title,
        context="Architecture discussions produce durable design choices, tradeoffs, and rejected alternatives.",
        decision="Create first-class governed Architecture Decision Records.",
        rationale="Future humans and agents need deterministic reasoning history without changing revision governance.",
        alternatives_considered=["Store rationale only in revision metadata", "Use freeform architecture notes"],
        consequences=["Architectural reasoning becomes retrievable", "Accepted ADRs require governance"],
        tradeoffs=["More records to maintain", "Clearer audit trail"],
        future_considerations=["Architecture principles can be derived later"],
        architecture_ids=[architecture_id],
        evidence_package_ids=["EVPKG-ARCHITECTURE-NAPKIN"],
        metadata={"test_sprint": "18.6"},
    )


def _approve(tmp_path: Path, proposal_id: str) -> str:
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(tmp_path).create_trace(
        decision_summary="Chair approved architecture decision record.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "session-18-6"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Evidence was sufficient for architecture decision record creation.",
    )
    return trace.trace_id


def test_adr_proposal_creates_governed_proposal_without_accepting_directly(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    adr = _propose(tmp_path, architecture_id)
    proposal = ProposalService(tmp_path).get_proposal(adr.proposal_id)

    assert adr.adr_id.startswith("ADR-")
    assert adr.adr_number == "ADR-0001"
    assert adr.status == "proposed"
    assert proposal.metadata["source"] == "architecture_adr_proposal"
    assert proposal.metadata["requires_chair_approval"] is True
    assert adr.metadata["direct_adr_acceptance"] is False
    assert architecture_id in adr.architecture_ids


def test_unapproved_proposal_cannot_accept_adr(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    adr = _propose(tmp_path, architecture_id)

    try:
        ArchitectureDecisionRecordService(tmp_path).accept_approved_adr(adr.adr_id, approved_by="chair")
    except PermissionError as exc:
        assert str(exc) == "approved_adr_proposal_required"
    else:
        raise AssertionError("unapproved proposals must not create accepted ADRs")

    assert ArchitectureDecisionRecordService(tmp_path).get_adr(adr.adr_id)["status"] == "proposed"


def test_approved_adr_is_accepted_with_lineage_and_retrievable_history(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    adr = _propose(tmp_path, architecture_id)
    trace_id = _approve(tmp_path, adr.proposal_id)

    accepted = ArchitectureDecisionRecordService(tmp_path).accept_approved_adr(adr.adr_id, approved_by="chair", decision_trace_id=trace_id)
    details = ArchitectureDecisionRecordService(tmp_path).get_adr(accepted.adr_id)
    history = ArchitectureDecisionRecordService(tmp_path).get_history(accepted.adr_id)

    assert accepted.status == "accepted"
    assert accepted.decision_trace_id == trace_id
    assert accepted.approved_by == "chair"
    assert details["metadata"]["accepted_adr_immutable"] is True
    assert history["count"] == 1
    assert history["history"][0]["adr_id"] == accepted.adr_id
    assert history["immutable_history"] is True


def test_superseding_adr_preserves_decision_history(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    first = _propose(tmp_path, architecture_id, "Use ADR governance")
    _approve(tmp_path, first.proposal_id)
    first = ArchitectureDecisionRecordService(tmp_path).accept_approved_adr(first.adr_id, approved_by="chair")

    second = ArchitectureDecisionRecordService(tmp_path).propose_adr(
        project_id="Ageix_Test",
        session_id="session-18-6",
        created_by="lex",
        title="Refine ADR governance",
        context="ADR governance needs explicit supersession history.",
        decision="Superseding ADRs replace accepted decisions through governance.",
        rationale="Accepted ADR content remains historically traceable.",
        architecture_ids=[architecture_id],
        supersedes_adr_id=first.adr_id,
    )
    _approve(tmp_path, second.proposal_id)
    second = ArchitectureDecisionRecordService(tmp_path).accept_approved_adr(second.adr_id, approved_by="chair")

    first_details = ArchitectureDecisionRecordService(tmp_path).get_adr(first.adr_id)
    history = ArchitectureDecisionRecordService(tmp_path).get_history(second.adr_id)

    assert second.adr_number == "ADR-0002"
    assert second.supersedes_adr_id == first.adr_id
    assert first_details["status"] == "superseded"
    assert [item["adr_id"] for item in history["history"]] == [first.adr_id, second.adr_id]


def test_adr_capabilities_are_registered_and_mcp_exposed(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    registry = CapabilityRegistryService(tmp_path)
    for capability_id in {
        "architecture.adr.propose",
        "architecture.adrs",
        "architecture.adr.details",
        "architecture.adr.history",
    }:
        assert registry.exists(capability_id)

    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.adr.propose" in tools
    assert "ageix.architecture.adrs" in tools
    assert "ageix.architecture.adr.details" in tools
    assert "ageix.architecture.adr.history" in tools

    proposed = facade.execute_tool("ageix.architecture.adr.propose", _context(), {
        "title": "MCP-origin ADR proposal",
        "context": "Lex and Greg architectural discussion produces an ADR draft.",
        "decision": "MCP may propose ADRs but cannot directly accept them.",
        "rationale": "Governance remains with proposal approval and internal acceptance.",
        "architecture_ids": [architecture_id],
        "evidence_package_ids": ["EVPKG-ARCHITECTURE-NAPKIN"],
    })
    assert proposed.success is True
    assert proposed.result["status"] == "proposed"
    assert proposed.result["proposal_id"].startswith("PROP-")

    listed = facade.execute_tool("ageix.architecture.adrs", _context(), {"project_id": "Ageix_Test"})
    details = facade.execute_tool("ageix.architecture.adr.details", _context(), {"adr_id": proposed.result["adr_id"]})
    history = facade.execute_tool("ageix.architecture.adr.history", _context(), {"adr_id": proposed.result["adr_id"]})

    assert listed.success is True
    assert listed.result["count"] == 1
    assert details.success is True
    assert details.result["title"] == "MCP-origin ADR proposal"
    assert history.success is True
    assert history.result["count"] == 1
