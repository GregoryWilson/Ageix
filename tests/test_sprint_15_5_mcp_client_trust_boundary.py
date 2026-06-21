from __future__ import annotations

from pathlib import Path

from ageix_mcp.clients import MCPClientHardeningAssessmentService
from ageix_mcp.facade_service import MCPFacadeService
from services.agent_session_service import AgentSessionService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService


PROJECT_ID = "Ageix_Test"


def _seed_project(tmp_path: Path) -> None:
    ProjectProfileService(tmp_path).register_project(PROJECT_ID, PROJECT_ID, "python", tmp_path)


def _ctx(
    session_id: str,
    *,
    client_id: str = "chatgpt",
    provider: str | None = "openai",
    agent_id: str = "lex",
    display_name: str | None = "Lex",
    claimed_primary: bool | None = None,
) -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id=client_id,
        provider=provider,
        agent_id=agent_id,
        display_name=display_name,
        claimed_primary=claimed_primary,
        participant_id="greg",
        session_id=session_id,
        project_id=PROJECT_ID,
    )


def _reasons(tmp_path: Path, session_id: str) -> list[str]:
    return [record["reason"] for record in CapabilityAuditService(tmp_path).list_records() if record["session_id"] == session_id]


def test_grok_is_never_allowed(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx("grok-denied", client_id="grok", provider="xai", agent_id="grok", display_name="Grok"),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_denylisted"]
    assert response.governance["security_violation"] is True
    assert "mcp_client_denylisted" in _reasons(tmp_path, "grok-denied")


def test_xai_cannot_impersonate_lex(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.identity.current",
        _ctx("xai-lex-denied", client_id="chatgpt", provider="xai", agent_id="lex", display_name="Lex"),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_denylisted"]
    assert response.governance["security_violation"] is True


def test_unknown_clients_denied_before_execution(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx("unknown-client", client_id="rogue", provider="rogue-ai", agent_id="rogue", display_name="Rogue"),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_unknown"]
    assert "mcp_client_unknown" in _reasons(tmp_path, "unknown-client")


def test_disabled_placeholder_clients_denied(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx("claude-placeholder", client_id="claude", provider="anthropic", agent_id="claude", display_name="Claude"),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_disabled"]
    assert response.metadata["client_trust"]["placeholder"] is True


def test_chatgpt_provider_mismatch_denied(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx("provider-mismatch", client_id="chatgpt", provider="anthropic", agent_id="lex", display_name="Lex"),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_provider_mismatch"]
    assert response.governance["security_violation"] is True


def test_lex_impersonation_by_name_denied(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.identity.current",
        _ctx("lex-name-spoof", client_id="custom", provider="custom", agent_id="lex", display_name="Lex"),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_disabled"]


def test_client_context_mutation_or_session_identity_drift_denied(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    good = _ctx("identity-drift")

    first = service.execute_tool("ageix.workflow.current", good, {})
    drift = service.execute_tool(
        "ageix.workflow.current",
        _ctx("identity-drift", client_id="chatgpt", provider="openai", agent_id="imposter", display_name="Lex"),
        {},
    )

    assert first.success is True
    assert drift.success is False
    assert drift.errors == ["mcp_client_agent_mismatch"]
    assert drift.governance["security_violation"] is True


def test_session_identity_drift_denied_for_persisted_provider_change(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    first = service.execute_tool("ageix.workflow.current", _ctx("provider-drift"), {})
    drift = service.execute_tool(
        "ageix.workflow.current",
        _ctx("provider-drift", client_id="chatgpt", provider="anthropic", agent_id="lex", display_name="Lex"),
        {},
    )

    assert first.success is True
    assert drift.success is False
    assert drift.errors == ["mcp_client_provider_mismatch"]


def test_trusted_client_repo_walk_attempt_denied_and_audited(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_capability(
        "repository.raw_read",
        _ctx("trusted-repo-walk"),
        {"path": "../../"},
        tool_name="ageix.capabilities.execute",
    )

    assert response.success is False
    assert response.governance["decision"] == "denied"
    assert response.governance["chair_authority_preserved"] is True
    assert _reasons(tmp_path, "trusted-repo-walk")


def test_workflow_bypass_attempt_still_denied_for_trusted_client(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.consultations.submit",
        _ctx("trusted-bypass"),
        {"consultation_type": "architecture_review"},
    )

    assert response.success is False
    assert response.errors == ["proposal_id_or_active_proposal_required"]
    assert response.governance["chair_authority_preserved"] is True


def test_admission_failures_preserve_audit_continuity(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    attempts = [
        _ctx("audit-admission", client_id="grok", provider="xai", agent_id="grok", display_name="Grok"),
        _ctx("audit-admission", client_id="rogue", provider="rogue", agent_id="rogue", display_name="Rogue"),
        _ctx("audit-admission", client_id="chatgpt", provider="anthropic", agent_id="lex", display_name="Lex"),
    ]

    for context in attempts:
        service.execute_tool("ageix.workflow.current", context, {})

    reasons = _reasons(tmp_path, "audit-admission")
    assert reasons == ["mcp_client_denylisted", "mcp_client_unknown", "mcp_client_provider_mismatch"]


def test_mcp_client_hardening_assessment():
    assessment = MCPClientHardeningAssessmentService().assess(
        client_id="chatgpt",
        validation={
            "denylist_enforced": True,
            "unknown_clients_denied": True,
            "placeholder_clients_denied": True,
            "provider_mismatch_denied": True,
            "impersonation_denied": True,
            "session_identity_drift_denied": True,
            "trusted_client_abuse_denied": True,
            "audit_failures_recorded": True,
        },
    )

    assert assessment["admission_hardened"] is True
    assert assessment["impersonation_hardened"] is True
    assert assessment["abuse_hardened"] is True
    assert assessment["audit_hardened"] is True
    assert assessment["hardened"] is True
    assert assessment["missing_checks"] == []
