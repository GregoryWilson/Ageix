from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-3-health",
        project_id="Ageix_Test",
    )

    print("\n== MCP HEALTH TOOL EXECUTION ==")

    response = service.execute_tool(
        tool_name="ageix.health",
        context=context,
        arguments={},
    )

    payload = response.model_dump()
    pprint(payload)

    assert payload["success"] is True
    assert payload["errors"] == []
    assert payload["metadata"]["tool_name"] == "ageix.health"
    assert payload["governance"]["capability_id"] == "ageix.health"
    assert payload["governance"]["tool_name"] == "ageix.health"
    assert payload["governance"]["authorized"] is True
    assert payload["governance"]["decision"] == "approved"
    assert payload["governance"]["chair_authority_preserved"] is True

    print("\nSmoke 3 PASS: MCP health tool routes through governed capability execution.")


if __name__ == "__main__":
    main()