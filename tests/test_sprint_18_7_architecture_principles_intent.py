from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_context_service import ArchitectureContextService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.capability_registry_service import CapabilityRegistryService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        session_id="session-18-7",
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
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Guidance", node_key="Guidance", parent_id=domain.architecture_id, node_type="component", description="Architecture guidance component.")
    return component.architecture_id


def _approve(tmp_path: Path, proposal_id: str) -> str:
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(tmp_path).create_trace(
        decision_summary="Chair approved architecture guidance artifact.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "session-18-7"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Evidence was sufficient for architecture guidance creation.",
    )
    return trace.trace_id


def test_principle_and_intent_proposals_reuse_governance_without_direct_acceptance(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    service = ArchitectureGuidanceService(tmp_path)

    principle = service.propose_principle(
        project_id="Ageix_Test",
        session_id="session-18-7",
        created_by="lex",
        title="Governance before autonomy",
        statement="External agents may propose architecture guidance but cannot directly mutate accepted guidance.",
        rationale="Guidance must preserve Chair authority and proposal lineage.",
        architecture_ids=[architecture_id],
        evidence_package_ids=["EVPKG-GUIDANCE-NAPKIN"],
        metadata={"test_sprint": "18.7"},
    )
    intent = service.propose_intent(
        project_id="Ageix_Test",
        session_id="session-18-7",
        created_by="lex",
        title="Small model architecture context",
        summary="Architecture guidance should help smaller models reason without reading the entire repository.",
        details="Intent records preserve long-term architectural direction separate from hard constraints.",
        architecture_ids=[architecture_id],
        principle_ids=[principle.principle_id],
        future_considerations=["Later evaluate work packets for intent alignment."],
    )

    assert principle.principle_id.startswith("ARCHPRIN-")
    assert principle.principle_number == "PRIN-0001"
    assert principle.status == "proposed"
    assert principle.metadata["direct_principle_acceptance"] is False
    assert ProposalService(tmp_path).get_proposal(principle.proposal_id).metadata["source"] == "architecture_principle_proposal"

    assert intent.intent_id.startswith("ARCHINTENT-")
    assert intent.intent_number == "INTENT-0001"
    assert intent.status == "proposed"
    assert intent.metadata["direct_intent_acceptance"] is False
    assert principle.principle_id in intent.principle_ids


def test_unapproved_guidance_cannot_be_accepted(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    service = ArchitectureGuidanceService(tmp_path)
    principle = service.propose_principle(project_id="Ageix_Test", session_id="session-18-7", created_by="lex", title="Immutable guidance", statement="Accepted guidance is immutable.", architecture_ids=[architecture_id])
    intent = service.propose_intent(project_id="Ageix_Test", session_id="session-18-7", created_by="lex", title="Guidance context", summary="Accepted guidance appears in architecture context.", architecture_ids=[architecture_id])

    try:
        service.accept_approved_principle(principle.principle_id, approved_by="chair")
    except PermissionError as exc:
        assert str(exc) == "approved_principle_proposal_required"
    else:
        raise AssertionError("unapproved principle proposals must not be accepted")

    try:
        service.accept_approved_intent(intent.intent_id, approved_by="chair")
    except PermissionError as exc:
        assert str(exc) == "approved_intent_proposal_required"
    else:
        raise AssertionError("unapproved intent proposals must not be accepted")


def test_accepted_guidance_is_retrievable_and_included_in_architecture_context(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    service = ArchitectureGuidanceService(tmp_path)
    principle = service.propose_principle(project_id="Ageix_Test", session_id="session-18-7", created_by="lex", title="Constraint vs direction", statement="Principles are constraints, not directional goals.", architecture_ids=[architecture_id])
    intent = service.propose_intent(project_id="Ageix_Test", session_id="session-18-7", created_by="lex", title="Direction vs constraint", summary="Intent describes long-term architectural direction.", architecture_ids=[architecture_id], principle_ids=[principle.principle_id])
    principle_trace = _approve(tmp_path, principle.proposal_id)
    intent_trace = _approve(tmp_path, intent.proposal_id)

    accepted_principle = service.accept_approved_principle(principle.principle_id, approved_by="chair", decision_trace_id=principle_trace)
    accepted_intent = service.accept_approved_intent(intent.intent_id, approved_by="chair", decision_trace_id=intent_trace)
    guidance = service.get_guidance(project_id="Ageix_Test", architecture_id=architecture_id)
    context = ArchitectureContextService(tmp_path).build_context(architecture_id)

    assert accepted_principle.status == "accepted"
    assert accepted_intent.status == "accepted"
    assert guidance["derived_guidance"] is True
    assert guidance["stored_guidance_artifact"] is False
    assert guidance["principle_count"] == 1
    assert guidance["intent_count"] == 1
    assert context.active_principles[0]["principle_id"] == principle.principle_id
    assert context.active_intents[0]["intent_id"] == intent.intent_id
    assert context.context_policy["active_guidance_included"] is True
    assert "active_principles=1" in context.summary


def test_guidance_supersession_preserves_history(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    service = ArchitectureGuidanceService(tmp_path)
    first = service.propose_principle(project_id="Ageix_Test", session_id="session-18-7", created_by="lex", title="Governed MCP", statement="MCP may propose but not accept guidance.", architecture_ids=[architecture_id])
    _approve(tmp_path, first.proposal_id)
    first = service.accept_approved_principle(first.principle_id, approved_by="chair")
    second = service.propose_principle(project_id="Ageix_Test", session_id="session-18-7", created_by="lex", title="Governed MCP refined", statement="MCP may propose guidance while internal governance controls acceptance and supersession.", architecture_ids=[architecture_id], supersedes_principle_id=first.principle_id)
    _approve(tmp_path, second.proposal_id)
    second = service.accept_approved_principle(second.principle_id, approved_by="chair")

    first_details = service.get_principle(first.principle_id)
    history = service.get_principle_history(second.principle_id)

    assert second.principle_number == "PRIN-0002"
    assert first_details["status"] == "superseded"
    assert [item["principle_id"] for item in history["history"]] == [first.principle_id, second.principle_id]
    assert history["immutable_history"] is True


def test_guidance_capabilities_are_registered_and_mcp_exposed(tmp_path: Path) -> None:
    architecture_id = _seed(tmp_path)
    registry = CapabilityRegistryService(tmp_path)
    for capability_id in {
        "architecture.principle.propose",
        "architecture.principles",
        "architecture.principle.details",
        "architecture.principle.history",
        "architecture.intent.propose",
        "architecture.intents",
        "architecture.intent.details",
        "architecture.intent.history",
        "architecture.guidance",
    }:
        assert registry.exists(capability_id)

    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.principle.propose" in tools
    assert "ageix.architecture.intent.propose" in tools
    assert "ageix.architecture.guidance" in tools

    proposed_principle = facade.execute_tool("ageix.architecture.principle.propose", _context(), {
        "title": "MCP-origin principle",
        "statement": "MCP can originate guidance proposals but cannot directly accept them.",
        "architecture_ids": [architecture_id],
    })
    proposed_intent = facade.execute_tool("ageix.architecture.intent.propose", _context(), {
        "title": "MCP-origin intent",
        "summary": "MCP-origin architectural discussions may become governed intent proposals.",
        "architecture_ids": [architecture_id],
        "principle_ids": [proposed_principle.result["principle_id"]],
    })
    listed_principles = facade.execute_tool("ageix.architecture.principles", _context(), {"project_id": "Ageix_Test"})
    listed_intents = facade.execute_tool("ageix.architecture.intents", _context(), {"project_id": "Ageix_Test"})
    details = facade.execute_tool("ageix.architecture.principle.details", _context(), {"principle_id": proposed_principle.result["principle_id"]})
    history = facade.execute_tool("ageix.architecture.intent.history", _context(), {"intent_id": proposed_intent.result["intent_id"]})
    guidance = facade.execute_tool("ageix.architecture.guidance", _context(), {"project_id": "Ageix_Test", "architecture_id": architecture_id})

    assert proposed_principle.success is True
    assert proposed_principle.result["status"] == "proposed"
    assert proposed_principle.result["proposal_id"].startswith("PROP-")
    assert proposed_intent.success is True
    assert listed_principles.result["count"] == 1
    assert listed_intents.result["count"] == 1
    assert details.result["title"] == "MCP-origin principle"
    assert history.result["count"] == 1
    assert guidance.result["derived_guidance"] is True
