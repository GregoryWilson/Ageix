from __future__ import annotations

from pathlib import Path
from typing import Any

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def build_fastmcp_server(repo_root: str | Path = ".") -> Any:
    """Build an Ageix FastMCP server when the optional transport is installed.

    The server is intentionally thin. Tool metadata comes from the MCP registry and
    all execution is delegated to the governed MCP facade/capability path.
    """
    try:
        from fastmcp import FastMCP  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional transport package
        raise RuntimeError("fastmcp_not_installed") from exc

    service = MCPService(repo_root)
    mcp = FastMCP("Ageix")

    for tool in service.tool_registry.list_tools():
        _register_tool(mcp, service, tool.name)

    return mcp


def _register_tool(mcp: Any, service: MCPService, tool_name: str) -> None:
    def invoke(context: dict[str, Any], arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed_context = AgeixRequestContext(**context)
        return service.execute_tool(tool_name, parsed_context, arguments or {}).model_dump()

    invoke.__name__ = tool_name.replace(".", "_")
    mcp.tool(name=tool_name)(invoke)
