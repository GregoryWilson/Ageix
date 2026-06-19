from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-2-placeholder",
        project_id="Ageix_Test",
    )

    print("\n== MCP PLACEHOLDER TOOL EXECUTION ==")

    for tool_name in [
        "ageix.validation.scenarios.list",
        "ageix.validation.scenario.request",
        "ageix.validation.result.get",
    ]:
        print(f"\n-- Executing {tool_name} --")
        response = service.execute_tool(
            tool_name=tool_name,
            context=context,
            arguments={"objective": "Smoke test placeholder validation sandbox contract."},
        )

        payload = response.model_dump()
        pprint(payload)

        assert payload["success"] is False
        assert "validation sandbox not yet implemented" in payload["errors"]
        assert payload["governance"]["denied"] is True
        assert payload["governance"]["security_violation"] is False
        assert payload["governance"]["chair_authority_preserved"] is True
        assert payload["metadata"]["placeholder"] is True
        assert payload["metadata"]["experimental"] is True

    print("\nSmoke 2 PASS: placeholder MCP tools are discoverable and return friendly governed errors.")


if __name__ == "__main__":
    main()