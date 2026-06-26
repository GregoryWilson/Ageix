from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-9-audit-trace",
        project_id="Ageix_Test",
    )

    print("\n== MCP AUDIT / TRACE SMOKE ==")

    print("\n-- Step 1: Execute governed health capability --")
    health = service.execute_tool(
        tool_name="ageix.health",
        context=context,
        arguments={},
    ).model_dump()

    pprint(health)

    assert health["success"] is True
    assert health["metadata"]["tool_name"] == "ageix.health"
    assert health["metadata"]["capability_id"] == "ageix.health"
    assert health["metadata"]["agent_id"] == "lex"
    assert health["metadata"]["session_id"] == "smoke-15-0-9-audit-trace"

    print("\n-- Step 2: Execute denied repository capability through MCP --")
    denied = service.execute_tool(
        tool_name="ageix.capabilities.execute",
        context=context,
        arguments={
            "capability_id": "repository.raw_read",
            "arguments": {
                "path": "services/capability_execution_service.py",
                "reason": "Smoke test audit trace for governed denial.",
            },
        },
    ).model_dump()

    pprint(denied)

    assert denied["success"] is False
    assert denied["metadata"]["tool_name"] == "ageix.capabilities.execute"
    assert denied["metadata"]["capability_id"] == "repository.raw_read"
    assert denied["metadata"]["agent_id"] == "lex"
    assert denied["metadata"]["session_id"] == "smoke-15-0-9-audit-trace"
    assert denied["governance"]["decision"] == "denied"
    assert denied["governance"]["authorization_reason"] == "external_agents_cannot_bypass_repository_governance"

    print("\n-- Step 3: Query recent audit records through MCP --")
    audit = service.execute_tool(
        tool_name="ageix.audit.recent",
        context=context,
        arguments={
            "limit": 10,
        },
    ).model_dump()

    pprint(audit)

    assert audit["success"] is True
    assert audit["metadata"]["tool_name"] == "ageix.audit.recent"
    assert audit["metadata"]["capability_id"] == "audit.recent"

    audit_text = str(audit)
    assert "smoke-15-0-9-audit-trace" in audit_text
    assert "repository.raw_read" in audit_text or "ageix.health" in audit_text

    print("\nSmoke 9 PASS: MCP actions are traceable through capability/audit visibility.")


if __name__ == "__main__":
    main()