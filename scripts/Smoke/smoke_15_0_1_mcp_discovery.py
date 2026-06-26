from pprint import pprint

from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    print("\n== MCP TOOL DISCOVERY ==")
    tools = service.tool_registry.discover()

    print(f"\nTool count: {len(tools)}\n")

    for tool in tools:
        print(f"- {tool['name']}")
        print(f"  capability_id: {tool.get('capability_id')}")
        print(f"  category:      {tool.get('category')}")
        print(f"  version:       {tool.get('version')}")
        print(f"  experimental:  {tool.get('experimental')}")
        print(f"  placeholder:   {tool.get('placeholder')}")
        print()

    print("== RAW TOOL DEFINITIONS ==")
    pprint(tools)


if __name__ == "__main__":
    main()