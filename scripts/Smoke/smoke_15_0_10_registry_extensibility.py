from pprint import pprint

from ageix_mcp.tool_definitions import MCPToolDefinition
from ageix_mcp.tool_registry import MCPToolRegistry


def main():
    print("\n== MCP REGISTRY EXTENSIBILITY ==")

    registry = MCPToolRegistry()

    before = registry.discover()
    before_count = len(before)

    smoke_tool = MCPToolDefinition(
        name="ageix.test.smoke",
        capability_id="test.smoke",
        category="test",
        description="Smoke test dynamically registered MCP tool.",
        version="1.0",
        requires_project=True,
        requires_auth=True,
        experimental=True,
    )

    registry.register(smoke_tool)

    after = registry.discover()
    after_count = len(after)

    print(f"\nBefore count: {before_count}")
    print(f"After count:  {after_count}")

    found = [tool for tool in after if tool["name"] == "ageix.test.smoke"]

    pprint(found)

    assert after_count == before_count + 1
    assert len(found) == 1
    assert found[0]["capability_id"] == "test.smoke"
    assert found[0]["category"] == "test"
    assert found[0]["experimental"] is True
    assert found[0]["enabled"] is True

    try:
        registry.register(smoke_tool)
        raise AssertionError("Expected duplicate tool registration to fail")
    except ValueError as exc:
        assert "duplicate_mcp_tool" in str(exc)
        print("\nDuplicate registration correctly rejected.")

    print("\nSmoke 10 PASS: MCP registry is extensible without server/facade changes.")


if __name__ == "__main__":
    main()