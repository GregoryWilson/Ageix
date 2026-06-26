from __future__ import annotations

from typing import Any

from models.capability_definition import CapabilityDefinition
from ageix_mcp.tool_definitions import MCPToolDefinition
from ageix_mcp.tool_registry import MCPToolRegistry
from services.capability_registry_service import CapabilityRegistryService


DISCOVERY_SCHEMA_VERSION = "1.0"


class MCPDiscoveryService:
    """Builds self-describing MCP discovery projections from governed metadata."""

    def __init__(self, tool_registry: MCPToolRegistry, capability_registry: CapabilityRegistryService) -> None:
        self.tool_registry = tool_registry
        self.capability_registry = capability_registry

    def discover_tools(
        self,
        *,
        category: str | None = None,
        experimental: bool | None = None,
        include_placeholders: bool = True,
        include_disabled: bool = False,
        exposed_only: bool = True,
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool in self.tool_registry.list_tools(include_disabled=include_disabled):
            capability = self.capability_registry.lookup(tool.capability_id)
            if exposed_only and capability is not None and not capability.exposed_to_external_agents:
                continue
            if category is not None and tool.category != category:
                continue
            if experimental is not None and tool.experimental is not experimental:
                continue
            if not include_placeholders and tool.placeholder:
                continue
            tools.append(self._project(tool, capability))
        return tools

    def categories(self, *, include_placeholders: bool = True, exposed_only: bool = True) -> list[dict[str, Any]]:
        tools = self.discover_tools(include_placeholders=include_placeholders, exposed_only=exposed_only)
        by_category: dict[str, int] = {}
        for tool in tools:
            by_category[str(tool["category"])] = by_category.get(str(tool["category"]), 0) + 1
        return [
            {"category": category, "tool_count": count, "discovery_schema_version": DISCOVERY_SCHEMA_VERSION}
            for category, count in sorted(by_category.items())
        ]

    def _project(self, tool: MCPToolDefinition, capability: CapabilityDefinition | None) -> dict[str, Any]:
        payload = tool.to_discovery_dict()
        capability_metadata = capability.model_dump() if capability is not None else {}
        payload.update({
            "discovery_schema_version": DISCOVERY_SCHEMA_VERSION,
            "access_level": capability_metadata.get("access_level", "reserved" if tool.placeholder else "unknown"),
            "requires_proposal": bool(capability_metadata.get("requires_proposal", False)),
            "requires_consultation": bool(capability_metadata.get("requires_consultation", False)),
            "exposed_to_external_agents": bool(capability_metadata.get("exposed_to_external_agents", True)),
            "capability_category": capability_metadata.get("category", tool.category),
            "capability_description": capability_metadata.get("description", tool.description),
            "capability_handler": capability_metadata.get("handler"),
            "governance_boundary": {
                "discovery_only": True,
                "grants_authority": False,
                "repository_access": False,
                "direct_execution": False,
                "chair_authority_preserved": True,
                "authorization_required_for_execution": True,
            },
            "metadata_ready_for_documentation": True,
        })
        return payload
