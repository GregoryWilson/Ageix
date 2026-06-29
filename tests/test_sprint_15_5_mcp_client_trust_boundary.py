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
    client_user_agent: str | None = None,
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
        client_user_agent=client_user_agent,
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


def test_claude_ai_connector_client_id_resolves_to_trusted_claude(tmp_path: Path):
    # Regression: the human-delegated connector is provisioned in Keycloak as
    # "ageix-connector-claude-ai" (KeycloakProvisioningService.provision_connector_client),
    # and that literal string arrives as the JWT azp claim / context.client_id. It must
    # resolve back to the registered "claude" client rather than being denied as unknown.
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx(
            "claude-ai-connector",
            client_id="ageix-connector-claude-ai",
            provider="anthropic",
            agent_id="claude",
            display_name="Claude",
        ),
        {},
    )

    assert response.success is True


def test_client_registry_resolves_connector_alias():
    from ageix_mcp.clients.client_registry import MCPClientRegistry

    registry = MCPClientRegistry()
    resolved = registry.get("ageix-connector-claude-ai")

    assert resolved is not None
    assert resolved.client_id == "claude"
    assert registry.get("ageix-connector-bogus") is None


def test_claude_code_connector_client_id_resolves_to_distinct_identity(tmp_path: Path):
    # Claude Code gets its own registry entry (distinct from claude.ai chat's "claude")
    # so dev-worker actions are audited and trust-scoped separately, even though both
    # are "Claude" to a human. Once Keycloak provisions "ageix-connector-claude-code",
    # the existing prefix-stripping resolution must find it without any alias-table entry.
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx(
            "claude-code-connector",
            client_id="ageix-connector-claude-code",
            provider="anthropic",
            agent_id="claude_code",
            display_name="Claude Code",
        ),
        {},
    )

    assert response.success is True


def test_client_registry_resolves_claude_code_without_alias_table_entry():
    from ageix_mcp.clients.client_registry import CONNECTOR_ID_ALIASES, MCPClientRegistry

    registry = MCPClientRegistry()
    resolved = registry.get("ageix-connector-claude-code")

    assert resolved is not None
    assert resolved.client_id == "claude-code"
    assert resolved.agent_id == "claude_code"
    assert "claude-code" not in CONNECTOR_ID_ALIASES


def test_claude_code_and_claude_ai_are_distinct_registry_entries():
    from ageix_mcp.clients.client_registry import MCPClientRegistry

    registry = MCPClientRegistry()
    claude_chat = registry.get("ageix-connector-claude-ai")
    claude_code = registry.get("ageix-connector-claude-code")

    assert claude_chat is not None
    assert claude_code is not None
    assert claude_chat.client_id != claude_code.client_id
    assert claude_chat.agent_id != claude_code.agent_id


def test_unprovisioned_connector_client_id_still_denied(tmp_path: Path):
    # The connector prefix alone must not grant trust -- only connector_ids with a
    # known alias to a registered client should resolve.
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx(
            "bogus-connector",
            client_id="ageix-connector-bogus",
            provider="bogus",
            agent_id="bogus",
            display_name="Bogus",
        ),
        {},
    )

    assert response.success is False
    assert response.errors == ["mcp_client_unknown"]


def test_disabled_placeholder_clients_denied(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx("gemini-placeholder", client_id="gemini", provider="google", agent_id="gemini", display_name="Gemini"),
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


def test_client_user_agent_surfaced_in_identity_current_result(tmp_path: Path):
    _seed_project(tmp_path)
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.identity.current",
        _ctx("user-agent-identity", client_user_agent="Claude-Code/1.0"),
        {},
    )

    assert response.success is True
    assert response.result["client_user_agent"] == "Claude-Code/1.0"


def test_client_user_agent_surfaced_in_audit_metadata(tmp_path: Path):
    _seed_project(tmp_path)
    MCPFacadeService(tmp_path).execute_tool(
        "ageix.workflow.current",
        _ctx("user-agent-audit", client_user_agent="claude-ai/1.0"),
        {},
    )

    records = [
        record for record in CapabilityAuditService(tmp_path).list_records()
        if record["session_id"] == "user-agent-audit"
    ]
    assert records
    assert records[-1]["metadata"]["client_user_agent"] == "claude-ai/1.0"


def test_client_user_agent_does_not_affect_session_identity_drift(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    first = service.execute_tool(
        "ageix.workflow.current",
        _ctx("user-agent-drift", client_user_agent="claude-ai/1.0"),
        {},
    )
    second = service.execute_tool(
        "ageix.workflow.current",
        _ctx("user-agent-drift", client_user_agent="Claude-Code/2.0"),
        {},
    )

    assert first.success is True
    assert second.success is True
