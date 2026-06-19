from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-4-capabilities-list",
        project_id="Ageix_Test",
    )

    print("\n== MCP CAPABILITIES LIST ==")

    response = service.execute_tool(
        tool_name="ageix.capabilities.list",
        context=context,
        arguments={},
    )

    payload = response.model_dump()
    pprint(payload)

    assert payload["success"] is True
    assert payload["errors"] == []
    assert payload["metadata"]["tool_name"] == "ageix.capabilities.list"
    assert payload["metadata"]["capability_id"] == "capabilities.list"

    assert "tools" in payload["result"]
    assert "capabilities" in payload["result"]

    tools = payload["result"]["tools"]
    capabilities = payload["result"]["capabilities"]

    print(f"\nTool count: {len(tools)}")
    print(f"Capability count: {len(capabilities)}")

    assert any(t["name"] == "ageix.health" for t in tools)
    assert any(t["name"] == "ageix.capabilities.execute" for t in tools)
    assert any(t["name"] == "ageix.validation.scenario.request" for t in tools)

    assert any(c["capability_id"] == "ageix.health" for c in capabilities)

    print("\nSmoke 4 PASS: MCP capability discovery returns both MCP tools and governed capability registry.")


if __name__ == "__main__":
    main()