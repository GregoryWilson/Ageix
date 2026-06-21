from __future__ import annotations

from collections.abc import Iterable

from ageix_mcp.tool_definitions import MCPToolDefinition, MCP_TOOL_DEFINITIONS


class MCPToolRegistry:
    """Metadata-driven registry for public Ageix MCP tool contracts."""

    TOOL_PREFIX = "ageix."

    def __init__(self, definitions: Iterable[MCPToolDefinition] | None = None) -> None:
        self._tools: dict[str, MCPToolDefinition] = {}
        for definition in definitions or MCP_TOOL_DEFINITIONS:
            self.register(definition)

    def register(self, definition: MCPToolDefinition) -> MCPToolDefinition:
        if not definition.name.startswith(self.TOOL_PREFIX):
            raise ValueError("mcp_tool_name_must_use_ageix_prefix")
        if not definition.capability_id:
            raise ValueError("mcp_tool_requires_capability_id")
        if definition.name in self._tools:
            raise ValueError(f"duplicate_mcp_tool:{definition.name}")
        self._tools[definition.name] = definition
        return definition

    def get(self, tool_name: str) -> MCPToolDefinition | None:
        return self._tools.get(tool_name)

    def require(self, tool_name: str) -> MCPToolDefinition:
        definition = self.get(tool_name)
        if definition is None:
            raise KeyError(tool_name)
        return definition

    def list_tools(self, *, include_disabled: bool = False) -> list[MCPToolDefinition]:
        tools = self._tools.values() if include_disabled else [tool for tool in self._tools.values() if tool.enabled]
        return sorted(tools, key=lambda item: item.name)

    def discover(
        self,
        *,
        category: str | None = None,
        experimental: bool | None = None,
        include_placeholders: bool = True,
        include_disabled: bool = False,
    ) -> list[dict[str, object]]:
        tools = []
        for tool in self.list_tools(include_disabled=include_disabled):
            if category is not None and tool.category != category:
                continue
            if experimental is not None and tool.experimental is not experimental:
                continue
            if not include_placeholders and tool.placeholder:
                continue
            tools.append(tool.to_discovery_dict())
        return tools

    def map_capability(self, tool_name: str) -> str | None:
        definition = self.get(tool_name)
        return definition.capability_id if definition else None
