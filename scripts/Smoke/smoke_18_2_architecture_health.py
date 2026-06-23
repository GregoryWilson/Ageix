from __future__ import annotations

from pathlib import Path
from pprint import pprint

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = ArchitectureRegistryService(repo_root)
    seed = registry.seed_official_ageix_architecture()

    context = AgeixRequestContext(
        session_id="smoke-18-2-session",
        agent_id="lex",
        project_id="Ageix",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(repo_root)
    tools = facade.discover_tools(category="architecture")
    tool_names = {tool["tool_name"] for tool in tools}

    health = facade.execute_tool("ageix.architecture.health", context, {"path": "Ageix.Architecture.ArchitectureHealth"})
    coverage = facade.execute_tool("ageix.architecture.coverage", context, {"project_id": "Ageix"})
    listed = facade.execute_tool("ageix.capabilities.list", context, {})
    listed_names = {tool["tool_name"] for tool in listed.result.get("tools", [])} if listed.success else set()

    report = {
        "seeded": seed.get("seeded"),
        "architecture_tool_count": len(tools),
        "health_tool_visible": "ageix.architecture.health" in tool_names,
        "coverage_tool_visible": "ageix.architecture.coverage" in tool_names,
        "health_success": health.success,
        "coverage_success": coverage.success,
        "node_health_status": (health.result.get("health") or {}).get("status") if health.success else None,
        "context_status": (health.result.get("health") or {}).get("context_status") if health.success else None,
        "coverage_status": coverage.result.get("coverage_status") if coverage.success else None,
        "mapped_components": coverage.result.get("mapped_components") if coverage.success else None,
        "capabilities_list_health_visible": "ageix.architecture.health" in listed_names,
        "capabilities_list_coverage_visible": "ageix.architecture.coverage" in listed_names,
    }

    print("== Smoke 18.2: Architecture health foundation ==")
    pprint(report)

    assert report["health_tool_visible"] is True
    assert report["coverage_tool_visible"] is True
    assert report["health_success"] is True
    assert report["coverage_success"] is True
    assert report["context_status"] in {"available", "failed"}
    assert report["coverage_status"] in {"partial", "substantial", "complete_current_state"}
    assert report["capabilities_list_health_visible"] is True
    assert report["capabilities_list_coverage_visible"] is True

    print("Smoke 18.2 PASS: deterministic architecture health, coverage, and MCP publication validated.")


if __name__ == "__main__":
    main()