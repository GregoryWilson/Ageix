from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex-participant-001",
        session_id="smoke-15-0-6-context-mapping",
        project_id="Ageix_Test",
    )

    print("\n== MCP SESSION CONTEXT MAPPING ==")

    response = service.execute_tool(
        tool_name="ageix.health",
        context=context,
        arguments={},
    )

    payload = response.model_dump()
    pprint(payload)

    assert payload["success"] is True
    assert payload["metadata"]["agent_id"] == "lex"
    assert payload["metadata"]["session_id"] == "smoke-15-0-6-context-mapping"
    assert payload["metadata"]["capability_id"] == "ageix.health"

    # These may be merged into request arguments instead of returned metadata.
    # So this smoke focuses on the fields proven visible after execution.
    assert payload["governance"]["tool_name"] == "ageix.health"
    assert payload["governance"]["capability_id"] == "ageix.health"
    assert payload["governance"]["authorized"] is True
    assert payload["governance"]["decision"] == "approved"

    print("\nSmoke 6 PASS: MCP context maps into governed capability execution.")


if __name__ == "__main__":
    main()