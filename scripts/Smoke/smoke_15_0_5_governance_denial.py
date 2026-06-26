from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-5-governance-denial",
        project_id="Ageix_Test",
    )

    print("\n== MCP GOVERNANCE DENIAL ==")

    response = service.execute_tool(
        tool_name="ageix.capabilities.execute",
        context=context,
        arguments={
            "capability_id": "repository.raw_read",
            "arguments": {
                "path": "services/capability_execution_service.py",
                "reason": "Smoke test MCP cannot bypass repository governance.",
            },
        },
    )

    payload = response.model_dump()
    pprint(payload)

    assert payload["success"] is False
    assert payload["errors"]
    assert payload["governance"]["capability_id"] == "repository.raw_read"
    assert payload["governance"]["tool_name"] == "ageix.capabilities.execute"
    assert payload["governance"]["authorized"] is False
    assert payload["governance"]["decision"] == "denied"
    assert payload["governance"]["chair_authority_preserved"] is True

    denial_text = " ".join(payload["errors"] + [str(payload["governance"].get("reason"))])
    assert "external_agents_cannot_bypass_repository_governance" in denial_text

    print("\nSmoke 5 PASS: MCP cannot bypass repository governance.")


if __name__ == "__main__":
    main()