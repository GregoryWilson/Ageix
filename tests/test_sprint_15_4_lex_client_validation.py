from __future__ import annotations

from pathlib import Path

from ageix_mcp.clients import ChatGPTClientProfile, ChatGPTClientSimulator, ClientReadinessService, MCPClientRegistry
from services.agent_session_service import AgentSessionService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService
from ageix_mcp.facade_service import MCPFacadeService


PROJECT_ID = "Ageix_Test"


def _seed_project(tmp_path: Path) -> None:
    ProjectProfileService(tmp_path).register_project(PROJECT_ID, PROJECT_ID, "python", tmp_path)


def test_client_registry():
    registry = MCPClientRegistry()
    clients = {client["client_id"]: client for client in registry.list_clients()}

    assert clients["chatgpt"]["display_name"] == "Lex"
    assert clients["chatgpt"]["provider"] == "openai"
    assert clients["chatgpt"]["enabled"] is True
    assert clients["chatgpt"]["primary"] is True
    assert clients["chatgpt"]["placeholder"] is False
    assert clients["claude"]["placeholder"] is True
    assert clients["gemini"]["enabled"] is False
    assert clients["openwebui"]["placeholder"] is True


def test_client_profile_resolution():
    profile = ChatGPTClientProfile.resolve(MCPClientRegistry())

    assert profile.client_id == "chatgpt"
    assert profile.display_name == "Lex"
    assert profile.provider == "openai"
    assert profile.governance_expectations["identity_grants_authority"] is False
    assert profile.discovery_behavior["hardcoded_workflow_paths_allowed"] is False


def test_chatgpt_discovery(tmp_path: Path):
    _seed_project(tmp_path)
    simulator = ChatGPTClientSimulator(str(tmp_path))
    tools = simulator.discover()
    categories = {tool["category"] for tool in tools}
    capabilities = {tool["capability_id"] for tool in tools}

    assert {"proposal", "consultation", "project", "workflow", "identity", "audit"}.issubset(categories)
    assert {"proposal.submit", "consultation.submit", "project.list", "workflow.current", "identity.current", "audit.recent"}.issubset(capabilities)


def test_chatgpt_schema_consumption(tmp_path: Path):
    _seed_project(tmp_path)
    snapshot = ChatGPTClientSimulator(str(tmp_path)).discovery_snapshot()

    assert snapshot["schemas"]["ageix.proposals.submit"]["required"] == ["objective"]
    assert "proposal_id" in snapshot["schemas"]["ageix.consultations.submit"]["required"]
    assert "ageix.consultations.submit" in snapshot["workflow_hints"]["ageix.proposals.submit"]


def test_chatgpt_workflow_navigation(tmp_path: Path):
    _seed_project(tmp_path)
    result = ChatGPTClientSimulator(str(tmp_path)).run_validation(project_id=PROJECT_ID)

    assert result.validation["workflow_navigation_succeeded"] is True
    assert result.validation["workflow_hints_consumed"] is True
    assert result.consumed_workflow_hints == ["ageix.consultations.submit", "ageix.proposals.status"]
    assert result.readiness["workflow_ready"] is True


def test_chatgpt_session_continuity(tmp_path: Path):
    _seed_project(tmp_path)
    result = ChatGPTClientSimulator(str(tmp_path)).run_validation(project_id=PROJECT_ID, session_id="lex-session-continuity")
    session = AgentSessionService(tmp_path).require_session("lex-session-continuity")

    assert result.validation["session_continuity_succeeded"] is True
    assert session.active_proposal_id is not None
    assert session.active_consultation_ids
    assert session.workflow_stage == "audit_reviewed"
    assert session.metadata["client_context"]["client_id"] == "chatgpt"
    assert session.metadata["client_context"]["authority_granted"] is False


def test_chatgpt_identity_continuity(tmp_path: Path):
    _seed_project(tmp_path)
    result = ChatGPTClientSimulator(str(tmp_path)).run_validation(project_id=PROJECT_ID, session_id="lex-identity")
    identity = result.responses["identity"]["result"]

    assert result.validation["identity_continuity_succeeded"] is True
    assert identity["client_id"] == "chatgpt"
    assert identity["provider"] == "openai"
    assert identity["governance_profile"] == "external_agent"
    assert identity["authority_boundary"]["identity_grants_authority"] is False


def test_chatgpt_governance_preservation(tmp_path: Path):
    _seed_project(tmp_path)
    result = ChatGPTClientSimulator(str(tmp_path)).run_validation(project_id=PROJECT_ID)

    assert result.validation["governance_denials_succeeded"] is True
    assert result.responses["restricted_capability_denial"]["success"] is False
    assert result.responses["restricted_capability_denial"]["governance"]["chair_authority_preserved"] is True


def test_chatgpt_denied_transitions(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    context = AgeixRequestContext(client_id="chatgpt", agent_id="lex", participant_id="greg", session_id="no-proposal", project_id=PROJECT_ID)

    response = service.execute_tool("ageix.consultations.submit", context, {"consultation_type": "architecture_review"})

    assert response.success is False
    assert response.errors == ["proposal_id_or_active_proposal_required"]
    assert response.governance["decision"] == "denied"
    assert response.governance["chair_authority_preserved"] is True


def test_chatgpt_audit_chain(tmp_path: Path):
    _seed_project(tmp_path)
    result = ChatGPTClientSimulator(str(tmp_path)).run_validation(project_id=PROJECT_ID, session_id="lex-audit")
    records = [record for record in CapabilityAuditService(tmp_path).list_records() if record["session_id"] == "lex-audit"]
    chain = [record["capability_id"] for record in records]

    assert result.validation["audit_continuity_succeeded"] is True
    assert chain[:5] == ["workflow.current", "identity.current", "proposal.submit", "consultation.submit", "proposal.status"]
    assert chain[-1] == "audit.recent"
    assert all(record["client_id"] == "chatgpt" for record in records)


def test_chatgpt_readiness_assessment():
    readiness = ClientReadinessService().assess(
        client_id="chatgpt",
        validation={
            "discovered_categories": ["proposal", "consultation", "project", "workflow", "identity", "audit"],
            "schema_consumed": True,
            "workflow_navigation_succeeded": True,
            "workflow_hints_consumed": True,
            "session_continuity_succeeded": True,
            "identity_continuity_succeeded": True,
            "governance_denials_succeeded": True,
            "audit_continuity_succeeded": True,
        },
    )

    assert readiness == {
        "client_id": "chatgpt",
        "discovery_ready": True,
        "workflow_ready": True,
        "session_ready": True,
        "identity_ready": True,
        "governance_ready": True,
        "audit_ready": True,
        "ready": True,
    }
