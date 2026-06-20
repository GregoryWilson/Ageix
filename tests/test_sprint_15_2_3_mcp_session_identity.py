from __future__ import annotations

from pathlib import Path

from mcp.facade_service import MCPFacadeService
from services.agent_session_service import AgentSessionService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService


def _seed_project(tmp_path: Path, project_id: str = "Ageix_Test") -> None:
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def _context(session_id: str = "sprint-15-2-3-session", project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id=session_id,
        project_id=project_id,
    )


def test_mcp_workflow_and_identity_tools_are_discoverable(tmp_path: Path):
    service = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"]: tool for tool in service.discover_tools()}

    assert "ageix.workflow.current" in tools
    assert "ageix.identity.current" in tools
    assert tools["ageix.workflow.current"]["access_level"] == "read"
    assert tools["ageix.identity.current"]["governance_boundary"]["grants_authority"] is False


def test_mcp_workflow_current_initializes_session_state(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)

    response = service.execute_tool("ageix.workflow.current", _context(), {})

    assert response.success is True
    assert response.result["session_id"] == "sprint-15-2-3-session"
    assert response.result["workflow_stage"] == "session_initialized"
    assert response.result["governance_boundary"]["session_context_grants_authority"] is False
    assert "ageix.proposals.submit" in response.result["recommended_next_tools"]


def test_mcp_proposal_submit_updates_active_workflow_context(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    context = _context()

    proposal_response = service.execute_tool(
        "ageix.proposals.submit",
        context,
        {"objective": "Validate MCP session workflow state.", "proposal_type": "architecture"},
    )
    workflow_response = service.execute_tool("ageix.workflow.current", context, {})

    assert proposal_response.success is True
    assert workflow_response.result["workflow_stage"] == "proposal_submitted"
    assert workflow_response.result["active_proposal_id"] == proposal_response.metadata["proposal_id"]
    assert "ageix.consultations.submit" in workflow_response.result["recommended_next_tools"]


def test_mcp_consultation_can_use_active_proposal_context(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    context = _context()

    proposal_response = service.execute_tool(
        "ageix.proposals.submit",
        context,
        {"objective": "Validate active proposal carry-forward.", "proposal_type": "architecture"},
    )
    consultation_response = service.execute_tool(
        "ageix.consultations.submit",
        context,
        {
            "consultation_type": "architecture_review",
            "summary": "Looks safe.",
            "confidence": 0.7,
            "disposition": "proceed",
            "evidence_sufficient": True,
        },
    )
    workflow_response = service.execute_tool("ageix.workflow.current", context, {})

    assert proposal_response.success is True
    assert consultation_response.success is True
    assert consultation_response.metadata["proposal_id"] == proposal_response.metadata["proposal_id"]
    assert workflow_response.result["workflow_stage"] == "consultation_submitted"
    assert consultation_response.metadata["consultation_id"] in workflow_response.result["active_consultation_ids"]


def test_mcp_consultation_transition_requires_proposal_context(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.consultations.submit",
        _context(session_id="no-active-proposal"),
        {"consultation_type": "architecture_review"},
    )

    assert response.success is False
    assert response.errors == ["proposal_id_or_active_proposal_required"]
    assert response.governance["decision"] == "denied"
    assert response.governance["chair_authority_preserved"] is True


def test_mcp_identity_current_reports_descriptive_identity_without_authority(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool("ageix.identity.current", _context(), {})

    assert response.success is True
    assert response.result["client_id"] == "chatgpt"
    assert response.result["provider"] == "openai"
    assert response.result["governance_profile"] == "external_agent"
    assert response.result["authority_boundary"]["identity_grants_authority"] is False
    assert response.result["authority_boundary"]["capability_governance_required"] is True


def test_mcp_session_audit_chain_continuity(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    context = _context(session_id="audit-chain-session")

    service.execute_tool("ageix.health", context, {})
    service.execute_tool("ageix.identity.current", context, {})
    service.execute_tool("ageix.workflow.current", context, {})

    records = [record for record in CapabilityAuditService(tmp_path).list_records() if record["session_id"] == "audit-chain-session"]
    assert [record["capability_id"] for record in records[-3:]] == ["ageix.health", "identity.current", "workflow.current"]
    assert all(record["client_id"] == "chatgpt" for record in records[-3:])


def test_agent_session_persists_identity_ready_workflow_fields(tmp_path: Path):
    _seed_project(tmp_path)
    context = _context(session_id="persisted-session")
    service = MCPFacadeService(tmp_path)

    service.execute_tool("ageix.health", context, {})
    session = AgentSessionService(tmp_path).get_session("persisted-session")

    assert session is not None
    assert session.last_tool == "ageix.health"
    assert session.workflow_stage == "health_checked"
    assert session.project_id == "Ageix_Test"
