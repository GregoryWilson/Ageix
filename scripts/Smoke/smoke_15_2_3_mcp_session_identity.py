#!/usr/bin/env python3
"""Sprint 15.2/15.3 MCP Session & Identity Intelligence smoke tests.

Run from repo root:
    PYTHONPATH=. python scripts/Smoke/smoke_15_2_3_mcp_session_identity.py
"""

from __future__ import annotations

from pathlib import Path
from pprint import pprint
from uuid import uuid4

from ageix_mcp.facade_service import MCPFacadeService
from services.agent_session_service import AgentSessionService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService


PROJECT_ID = "Ageix_Test"
CLIENT_ID = "chatgpt"
AGENT_ID = "lex"
PARTICIPANT_ID = "greg"


def _repo_root() -> Path:
    return Path.cwd().resolve()


def _seed_project(repo_root: Path) -> None:
    try:
        ProjectProfileService(repo_root).register_project(
            project_id=PROJECT_ID,
            name=PROJECT_ID,
            project_type="python",
            root_path=repo_root,
        )
    except Exception as exc:
        if "Project already registered" not in str(exc):
            raise


def _context(session_id: str) -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id=CLIENT_ID,
        agent_id=AGENT_ID,
        participant_id=PARTICIPANT_ID,
        session_id=session_id,
        project_id=PROJECT_ID,
    )


def _new_session(label: str) -> str:
    return f"smoke-15-2-3-{label}-{uuid4().hex[:8]}"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _submit_proposal_for_session(service: MCPFacadeService, session_id: str, objective: str) -> str:
    response = service.execute_tool(
        "ageix.proposals.submit",
        _context(session_id),
        {"objective": objective, "proposal_type": "architecture"},
    )
    _assert(response.success is True, f"proposal submit failed: {response.errors}")
    proposal_id = response.metadata.get("proposal_id") or response.result.get("proposal_id")
    _assert(bool(proposal_id), "proposal submit did not return a proposal_id")
    return str(proposal_id)


def smoke_1_tools_discoverable(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.2/15.3.1: Workflow and identity tools discoverable ==")
    tools = {tool["tool_name"]: tool for tool in service.discover_tools()}
    workflow = tools.get("ageix.workflow.current")
    identity = tools.get("ageix.identity.current")

    _assert(workflow is not None, "ageix.workflow.current was not discoverable")
    _assert(identity is not None, "ageix.identity.current was not discoverable")
    _assert(workflow["category"] == "workflow", "workflow tool category mismatch")
    _assert(identity["category"] == "identity", "identity tool category mismatch")
    _assert(workflow["access_level"] == "read", "workflow tool should be read access")
    _assert(identity["governance_boundary"]["grants_authority"] is False, "identity discovery must not grant authority")

    pprint({
        "workflow": {
            "tool_name": workflow["tool_name"],
            "category": workflow["category"],
            "access_level": workflow["access_level"],
            "recommended_next_tools": workflow["recommended_next_tools"],
            "grants_authority": workflow["governance_boundary"]["grants_authority"],
        },
        "identity": {
            "tool_name": identity["tool_name"],
            "category": identity["category"],
            "access_level": identity["access_level"],
            "related_tools": identity["related_tools"],
            "grants_authority": identity["governance_boundary"]["grants_authority"],
        },
    })
    print("Smoke 15.2/15.3.1 PASS")


def smoke_2_workflow_initializes_session(repo_root: Path, service: MCPFacadeService) -> str:
    print("\n== Smoke 15.2/15.3.2: Workflow current initializes session state ==")
    session_id = _new_session("workflow-init")
    response = service.execute_tool("ageix.workflow.current", _context(session_id), {})

    _assert(response.success is True, f"workflow.current failed: {response.errors}")
    result = response.result
    _assert(result["session_id"] == session_id, "workflow session_id mismatch")
    _assert(result["agent_id"] == AGENT_ID, "workflow agent_id mismatch")
    _assert(result["project_id"] == PROJECT_ID, "workflow project_id mismatch")
    _assert(result["workflow_stage"] == "session_initialized", "new session should initialize as session_initialized")
    _assert(result["governance_boundary"]["session_context_grants_authority"] is False, "session context must not grant authority")
    _assert("ageix.proposals.submit" in result["recommended_next_tools"], "initial workflow should recommend proposal submission")

    persisted = AgentSessionService(repo_root).get_session(session_id)
    _assert(persisted is not None, "workflow.current did not persist the session")

    pprint(result)
    print("Smoke 15.2/15.3.2 PASS")
    return session_id


def smoke_3_identity_current_describes_caller(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.2/15.3.3: Identity current describes caller without authority ==")
    session_id = _new_session("identity")
    response = service.execute_tool("ageix.identity.current", _context(session_id), {})

    _assert(response.success is True, f"identity.current failed: {response.errors}")
    result = response.result
    _assert(result["client_id"] == CLIENT_ID, "identity client_id mismatch")
    _assert(result["provider"] == "openai", "chatgpt client should map to openai provider")
    _assert(result["agent_id"] == AGENT_ID, "identity agent_id mismatch")
    _assert(result["governance_profile"] == "external_agent", "expected external_agent governance profile")
    _assert(result["authority_boundary"]["identity_grants_authority"] is False, "identity must not grant authority")
    _assert(result["authority_boundary"]["capability_governance_required"] is True, "capability governance must remain required")
    _assert(result["authority_boundary"]["chair_authority_preserved"] is True, "Chair authority must be preserved")

    pprint(result)
    print("Smoke 15.2/15.3.3 PASS")


def smoke_4_proposal_updates_workflow_context(service: MCPFacadeService) -> tuple[str, str]:
    print("\n== Smoke 15.2/15.3.4: Proposal submit updates active workflow context ==")
    session_id = _new_session("proposal")
    context = _context(session_id)
    proposal_id = _submit_proposal_for_session(
        service,
        session_id,
        "Smoke validate MCP session workflow state.",
    )

    workflow_response = service.execute_tool("ageix.workflow.current", context, {})
    _assert(workflow_response.success is True, f"workflow.current failed after proposal: {workflow_response.errors}")
    result = workflow_response.result
    _assert(result["workflow_stage"] == "proposal_submitted", "workflow stage should be proposal_submitted")
    _assert(result["active_proposal_id"] == proposal_id, "active proposal was not carried into workflow state")
    _assert("ageix.consultations.submit" in result["recommended_next_tools"], "proposal stage should recommend consultation submit")

    pprint({"proposal_id": proposal_id, "workflow": result})
    print("Smoke 15.2/15.3.4 PASS")
    return session_id, str(proposal_id)


def smoke_5_consultation_uses_active_proposal(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.2/15.3.5: Consultation uses active proposal context ==")
    session_id = _new_session("consultation")
    proposal_id = _submit_proposal_for_session(
        service,
        session_id,
        "Smoke validate active proposal carry-forward.",
    )
    context = _context(session_id)

    consultation_response = service.execute_tool(
        "ageix.consultations.submit",
        context,
        {
            "consultation_type": "architecture_review",
            "summary": "Smoke test confirms active proposal context carry-forward.",
            "confidence": 0.75,
            "disposition": "proceed",
            "evidence_sufficient": True,
        },
    )
    _assert(consultation_response.success is True, f"consultation submit failed: {consultation_response.errors}")
    _assert(consultation_response.metadata.get("proposal_id") == proposal_id, "consultation did not use active proposal_id")
    consultation_id = consultation_response.metadata.get("consultation_id") or consultation_response.result.get("consultation_id")
    _assert(bool(consultation_id), "consultation submit did not return consultation_id")

    workflow_response = service.execute_tool("ageix.workflow.current", context, {})
    result = workflow_response.result
    _assert(result["workflow_stage"] == "consultation_submitted", "workflow stage should be consultation_submitted")
    _assert(str(consultation_id) in result["active_consultation_ids"], "active consultation was not tracked")

    pprint({
        "proposal_id": proposal_id,
        "consultation_id": consultation_id,
        "workflow_stage": result["workflow_stage"],
        "active_consultation_ids": result["active_consultation_ids"],
        "recommended_next_tools": result["recommended_next_tools"],
    })
    print("Smoke 15.2/15.3.5 PASS")


def smoke_6_transition_denial_preserves_governance(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.2/15.3.6: Consultation transition requires proposal context ==")
    session_id = _new_session("transition-denial")
    response = service.execute_tool(
        "ageix.consultations.submit",
        _context(session_id),
        {
            "consultation_type": "architecture_review",
            "summary": "This should be denied because no proposal context exists.",
        },
    )

    _assert(response.success is False, "consultation without proposal context should fail")
    _assert(response.errors == ["proposal_id_or_active_proposal_required"], "unexpected transition denial reason")
    _assert(response.governance["decision"] == "denied", "governance decision should be denied")
    _assert(response.governance["chair_authority_preserved"] is True, "Chair authority should be preserved on denial")

    pprint({"errors": response.errors, "governance": response.governance, "metadata": response.metadata})
    print("Smoke 15.2/15.3.6 PASS")


def smoke_7_session_audit_chain(repo_root: Path, service: MCPFacadeService) -> None:
    print("\n== Smoke 15.2/15.3.7: Session audit chain continuity ==")
    session_id = _new_session("audit-chain")
    context = _context(session_id)

    service.execute_tool("ageix.health", context, {})
    service.execute_tool("ageix.identity.current", context, {})
    service.execute_tool("ageix.workflow.current", context, {})

    records = [record for record in CapabilityAuditService(repo_root).list_records() if record.get("session_id") == session_id]
    last_three = records[-3:]
    _assert([record["capability_id"] for record in last_three] == ["ageix.health", "identity.current", "workflow.current"], "audit chain capability order mismatch")
    _assert(all(record.get("client_id") == CLIENT_ID for record in last_three), "audit chain client_id mismatch")
    _assert(all(record.get("agent_id") == AGENT_ID for record in last_three), "audit chain agent_id mismatch")

    pprint(last_three)
    print("Smoke 15.2/15.3.7 PASS")


def smoke_8_session_persistence(repo_root: Path, service: MCPFacadeService) -> None:
    print("\n== Smoke 15.2/15.3.8: Session persistence records identity-ready workflow fields ==")
    session_id = _new_session("persist")
    service.execute_tool("ageix.health", _context(session_id), {})
    session = AgentSessionService(repo_root).get_session(session_id)

    _assert(session is not None, "session was not persisted")
    _assert(session.last_tool == "ageix.health", "session last_tool was not persisted")
    _assert(session.workflow_stage == "health_checked", "session workflow_stage was not persisted")
    _assert(session.project_id == PROJECT_ID, "session project_id was not persisted")
    _assert("ageix.health" in session.capabilities_used, "session capabilities_used did not include health")

    pprint(session.model_dump())
    print("Smoke 15.2/15.3.8 PASS")


def main() -> None:
    repo_root = _repo_root()
    _seed_project(repo_root)
    service = MCPFacadeService(repo_root)

    smoke_1_tools_discoverable(service)
    smoke_2_workflow_initializes_session(repo_root, service)
    smoke_3_identity_current_describes_caller(service)
    smoke_4_proposal_updates_workflow_context(service)
    smoke_5_consultation_uses_active_proposal(service)
    smoke_6_transition_denial_preserves_governance(service)
    smoke_7_session_audit_chain(repo_root, service)
    smoke_8_session_persistence(repo_root, service)

    print("\nALL SPRINT 15.2/15.3 MCP SESSION & IDENTITY SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
