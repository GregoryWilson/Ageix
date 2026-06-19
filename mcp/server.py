from __future__ import annotations

from pathlib import Path
from typing import Any

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def build_fastmcp_server(repo_root: str | Path = ".") -> Any:
    """Build a FastMCP server when fastmcp is installed.

    The import is intentionally lazy so Ageix core tests and HTTP service startup do
    not require MCP transport packages unless an MCP server is actually launched.
    """
    try:
        from fastmcp import FastMCP  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional transport package
        raise RuntimeError("fastmcp_not_installed") from exc

    service = MCPService(repo_root)
    mcp = FastMCP("Ageix")

    @mcp.tool(name="ageix.capabilities.list")
    def capabilities_list() -> dict[str, Any]:
        return {"success": True, "result": {"tools": service.discover_tools(), "capabilities": service.list_capabilities()}}

    @mcp.tool(name="ageix.capabilities.execute")
    def capabilities_execute(context: dict[str, Any], capability_id: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed_context = AgeixRequestContext(**context)
        return service.execute_capability(capability_id, parsed_context, arguments or {}).model_dump()

    @mcp.tool(name="ageix.proposals.submit")
    def proposals_submit(context: dict[str, Any], objective: str, proposal_type: str = "investigation", arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed_context = AgeixRequestContext(**context)
        return service.execute_capability("proposal.submit", parsed_context, {**(arguments or {}), "objective": objective, "proposal_type": proposal_type}).model_dump()

    @mcp.tool(name="ageix.consultations.submit")
    def consultations_submit(context: dict[str, Any], proposal_id: str, consultation_type: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed_context = AgeixRequestContext(**context)
        return service.execute_capability("consultation.submit", parsed_context, {**(arguments or {}), "proposal_id": proposal_id, "consultation_type": consultation_type}).model_dump()

    return mcp
