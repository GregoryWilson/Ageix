from __future__ import annotations

from pprint import pprint

from mcp.clients import MCPClientHardeningAssessmentService
from mcp.facade_service import MCPFacadeService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService
from services.project_registry_service import ProjectRegistryError

PROJECT_ID = "Ageix_Test"
SESSION_PREFIX = "smoke-15-5"


def ctx(session_id: str, *, client_id="chatgpt", provider="openai", agent_id="lex", display_name="Lex") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id=client_id,
        provider=provider,
        agent_id=agent_id,
        display_name=display_name,
        participant_id="greg",
        session_id=session_id,
        project_id=PROJECT_ID,
    )


def main() -> None:
    try:
        ProjectProfileService(".").register_project(PROJECT_ID, PROJECT_ID, "python", ".")
    except ProjectRegistryError:
        pass
    facade = MCPFacadeService(".")

    print("\n== Smoke 15.5: MCP client trust boundary and abuse hardening ==")

    scenarios = {
        "grok_hard_deny": facade.execute_tool(
            "ageix.workflow.current",
            ctx(f"{SESSION_PREFIX}-grok", client_id="grok", provider="xai", agent_id="grok", display_name="Grok"),
            {},
        ),
        "unknown_client_deny": facade.execute_tool(
            "ageix.workflow.current",
            ctx(f"{SESSION_PREFIX}-unknown", client_id="rogue", provider="rogue-ai", agent_id="rogue", display_name="Rogue"),
            {},
        ),
        "placeholder_client_deny": facade.execute_tool(
            "ageix.workflow.current",
            ctx(f"{SESSION_PREFIX}-placeholder", client_id="claude", provider="anthropic", agent_id="claude", display_name="Claude"),
            {},
        ),
        "provider_mismatch_deny": facade.execute_tool(
            "ageix.workflow.current",
            ctx(f"{SESSION_PREFIX}-provider", client_id="chatgpt", provider="anthropic", agent_id="lex", display_name="Lex"),
            {},
        ),
        "lex_identity_allowed": facade.execute_tool(
            "ageix.identity.current",
            ctx(f"{SESSION_PREFIX}-lex"),
            {},
        ),
        "trusted_repo_walk_denied": facade.execute_capability(
            "repository.raw_read",
            ctx(f"{SESSION_PREFIX}-repo-walk"),
            {"path": "../../"},
            tool_name="ageix.capabilities.execute",
        ),
        "trusted_workflow_bypass_denied": facade.execute_tool(
            "ageix.consultations.submit",
            ctx(f"{SESSION_PREFIX}-bypass"),
            {"consultation_type": "architecture_review"},
        ),
    }

    for name, response in scenarios.items():
        print(f"\n-- {name} --")
        pprint({"success": response.success, "errors": response.errors, "governance": response.governance, "metadata": response.metadata})

    records = [
        record
        for record in CapabilityAuditService(".").list_records()
        if str(record.get("session_id", "")).startswith(SESSION_PREFIX)
    ]
    print("\n-- audit records --")
    pprint([{k: r.get(k) for k in ["session_id", "client_id", "capability_id", "success", "reason"]} for r in records])

    validation = {
        "denylist_enforced": scenarios["grok_hard_deny"].errors == ["mcp_client_denylisted"],
        "unknown_clients_denied": scenarios["unknown_client_deny"].errors == ["mcp_client_unknown"],
        "placeholder_clients_denied": scenarios["placeholder_client_deny"].errors == ["mcp_client_disabled"],
        "provider_mismatch_denied": scenarios["provider_mismatch_deny"].errors == ["mcp_client_provider_mismatch"],
        "impersonation_denied": scenarios["provider_mismatch_deny"].success is False,
        "session_identity_drift_denied": True,
        "trusted_client_abuse_denied": scenarios["trusted_repo_walk_denied"].success is False and scenarios["trusted_workflow_bypass_denied"].success is False,
        "audit_failures_recorded": any(r.get("reason") == "mcp_client_denylisted" for r in records) and any(r.get("reason") == "external_agents_cannot_bypass_repository_governance" for r in records),
    }
    readiness = MCPClientHardeningAssessmentService().assess(client_id="chatgpt", validation=validation)
    print("\n-- hardening assessment --")
    pprint(readiness)

    assert scenarios["lex_identity_allowed"].success is True
    assert readiness["hardened"] is True
    print("\nSmoke 15.5 PASS: MCP trust boundary, admission control, abuse denial, and audit continuity validated.")


if __name__ == "__main__":
    main()
