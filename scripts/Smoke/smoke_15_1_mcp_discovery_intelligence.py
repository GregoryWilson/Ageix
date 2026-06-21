"""
Ageix Sprint 15.1 smoke tests: MCP Discovery Intelligence

Run from repo root:

    PYTHONPATH=. python scratch/smoke_15_1_mcp_discovery_intelligence.py

Or, if copied elsewhere:

    PYTHONPATH=/path/to/ageix python /path/to/smoke_15_1_mcp_discovery_intelligence.py

Purpose:
- Validate richer MCP discovery metadata
- Validate input schema exposure
- Validate category / experimental / placeholder filtering
- Validate workflow relationship hints
- Validate governance metadata is discovery-only and does not grant authority
- Validate non-exposed capabilities stay hidden from external discovery
"""

from __future__ import annotations

from pathlib import Path
from pprint import pprint

from ageix_mcp.discovery_service import DISCOVERY_SCHEMA_VERSION, MCPDiscoveryService
from ageix_mcp.facade_service import MCPFacadeService
from ageix_mcp.tool_definitions import MCPToolDefinition
from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_definition import CapabilityDefinition
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_tool(tools: list[dict], tool_name: str) -> dict:
    for tool in tools:
        if tool.get("tool_name") == tool_name or tool.get("name") == tool_name:
            return tool
    raise AssertionError(f"Tool not found in discovery: {tool_name}")


def seed_project(repo_root: Path, project_id: str = "Ageix_Test") -> None:
    service = ProjectProfileService(repo_root)
    try:
        service.register_project(
            project_id=project_id,
            name=project_id,
            project_type="python",
            root_path=repo_root,
        )
    except Exception as exc:
        if "already registered" not in str(exc):
            raise


def context(project_id: str | None = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="smoke-15-1-discovery-session",
        project_id=project_id,
    )


def smoke_1_discovery_metadata(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.1.1: Discovery metadata ==")
    proposal = find_tool(service.discover_tools(), "ageix.proposals.submit")
    pprint({
        "tool_name": proposal["tool_name"],
        "category": proposal["category"],
        "version": proposal["version"],
        "discovery_schema_version": proposal["discovery_schema_version"],
        "access_level": proposal["access_level"],
        "requires_project": proposal["requires_project"],
        "requires_auth": proposal["requires_auth"],
        "requires_proposal": proposal["requires_proposal"],
        "requires_consultation": proposal["requires_consultation"],
        "exposed_to_external_agents": proposal["exposed_to_external_agents"],
        "metadata_ready_for_documentation": proposal["metadata_ready_for_documentation"],
    })

    require(proposal["discovery_schema_version"] == DISCOVERY_SCHEMA_VERSION, "Missing/invalid discovery schema version")
    require(proposal["category"] == "proposal", "Proposal submit category should be proposal")
    require(proposal["access_level"] == "governed_read", "Proposal submit access level should map from capability metadata")
    require(proposal["requires_project"] is True, "Proposal submit should require project")
    require(proposal["requires_auth"] is True, "Proposal submit should require auth")
    require(proposal["requires_proposal"] is True, "Capability metadata should expose proposal requirement")
    require(proposal["exposed_to_external_agents"] is True, "Proposal submit should be exposed externally")
    print("Smoke 15.1.1 PASS")


def smoke_2_input_schema(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.1.2: Input schema exposure ==")
    proposal = find_tool(service.discover_tools(), "ageix.proposals.submit")
    schema = proposal["input_schema"]
    pprint(schema)

    require(schema["type"] == "object", "Input schema should use object shape")
    require("objective" in schema["required"], "objective should be required")
    require(schema["properties"]["objective"]["type"] == "string", "objective should be a string")
    require("architecture" in schema["properties"]["proposal_type"]["enum"], "proposal_type should expose enum values")
    print("Smoke 15.1.2 PASS")


def smoke_3_discovery_filtering(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.1.3: Discovery filtering ==")
    proposal_tools = service.discover_tools(category="proposal")
    non_experimental = service.discover_tools(experimental=False)
    without_placeholders = service.discover_tools(include_placeholders=False)

    summary = {
        "proposal_tool_count": len(proposal_tools),
        "non_experimental_count": len(non_experimental),
        "without_placeholders_count": len(without_placeholders),
        "without_placeholders_names": [tool["tool_name"] for tool in without_placeholders],
    }
    pprint(summary)

    require(proposal_tools, "Expected proposal tools")
    require({tool["category"] for tool in proposal_tools} == {"proposal"}, "Category filter returned non-proposal tools")
    require(non_experimental, "Expected non-experimental tools")
    require(all(tool["experimental"] is False for tool in non_experimental), "Experimental filter failed")
    require(all(tool["placeholder"] is False for tool in without_placeholders), "Placeholder filter failed")
    require(
        "ageix.validation.scenario.request" not in {tool["tool_name"] for tool in without_placeholders},
        "Validation placeholder request should be hidden when include_placeholders=False",
    )
    print("Smoke 15.1.3 PASS")


def smoke_4_categories(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.1.4: Discovery categories ==")
    categories = service.discover_categories()
    pprint(categories)

    names = {item["category"] for item in categories}
    for expected in {"system", "capability", "project", "proposal", "consultation", "audit", "validation"}:
        require(expected in names, f"Missing discovery category: {expected}")
    require(all(item["tool_count"] > 0 for item in categories), "Every category should report at least one tool")
    require(all(item["discovery_schema_version"] == DISCOVERY_SCHEMA_VERSION for item in categories), "Category schema version mismatch")
    print("Smoke 15.1.4 PASS")


def smoke_5_workflow_relationships(service: MCPFacadeService) -> None:
    print("\n== Smoke 15.1.5: Workflow relationships ==")
    proposal = find_tool(service.discover_tools(), "ageix.proposals.submit")
    validation = find_tool(service.discover_tools(), "ageix.validation.scenario.request")
    pprint({
        "proposal_recommended_next_tools": proposal["workflow"]["recommended_next_tools"],
        "proposal_related_tools": proposal["workflow"]["related_tools"],
        "validation_recommended_next_tools": validation["workflow"]["recommended_next_tools"],
    })

    require("ageix.proposals.status" in proposal["recommended_next_tools"], "Proposal submit should recommend proposal status")
    require("ageix.consultations.submit" in proposal["workflow"]["recommended_next_tools"], "Proposal submit should recommend consultation submit")
    require("ageix.proposals.get" in proposal["related_tools"], "Proposal submit should expose related proposal get")
    require("ageix.validation.result.get" in validation["workflow"]["recommended_next_tools"], "Validation request should recommend result get")
    print("Smoke 15.1.5 PASS")


def smoke_6_governance_boundary_and_execution(service: MCPFacadeService, repo_root: Path) -> None:
    print("\n== Smoke 15.1.6: Discovery preserves governance boundary ==")
    seed_project(repo_root)
    health = find_tool(service.discover_tools(), "ageix.health")
    pprint(health["governance_boundary"])

    require(health["governance_boundary"]["discovery_only"] is True, "Discovery boundary should be marked discovery-only")
    require(health["governance_boundary"]["grants_authority"] is False, "Discovery must not grant authority")
    require(health["governance_boundary"]["repository_access"] is False, "Discovery must not imply repository access")
    require(health["governance_boundary"]["direct_execution"] is False, "Discovery must not imply direct execution")
    require(health["governance_boundary"]["chair_authority_preserved"] is True, "Chair authority should be preserved")

    response = service.execute_tool("ageix.health", context(), {})
    pprint({"success": response.success, "governance": response.governance, "metadata": response.metadata})
    require(response.success is True, "Health execution should still work")
    require(response.governance["chair_authority_preserved"] is True, "Execution governance should still preserve Chair authority")
    print("Smoke 15.1.6 PASS")


def smoke_7_hidden_capability_not_discovered(repo_root: Path) -> None:
    print("\n== Smoke 15.1.7: Non-exposed capability hidden from external discovery ==")
    tool_registry = MCPToolRegistry(definitions=[
        MCPToolDefinition(
            name="ageix.hidden.tool",
            capability_id="hidden.tool",
            category="hidden",
            description="Hidden tool should not be discoverable externally.",
        )
    ])
    capability_registry = CapabilityRegistryService(repo_root)
    capability_registry.register(
        CapabilityDefinition(
            capability_id="hidden.tool",
            category="hidden",
            access_level="internal",
            handler="hidden.tool",
            description="Internal capability.",
            exposed_to_external_agents=False,
        ),
        lambda arguments: {"success": True, "result": {}},
    )
    discovery = MCPDiscoveryService(tool_registry, capability_registry)

    external = discovery.discover_tools()
    internal = discovery.discover_tools(exposed_only=False)
    pprint({"external_discovery": external, "internal_discovery": internal})

    require(external == [], "Hidden tool should not appear in default external discovery")
    require(len(internal) == 1, "Hidden tool should appear only when exposed_only=False")
    require(internal[0]["exposed_to_external_agents"] is False, "Hidden capability metadata should remain false")
    print("Smoke 15.1.7 PASS")


def main() -> None:
    repo_root = Path.cwd().resolve()
    service = MCPFacadeService(repo_root)

    smoke_1_discovery_metadata(service)
    smoke_2_input_schema(service)
    smoke_3_discovery_filtering(service)
    smoke_4_categories(service)
    smoke_5_workflow_relationships(service)
    smoke_6_governance_boundary_and_execution(service, repo_root)
    smoke_7_hidden_capability_not_discovered(repo_root)

    print("\nALL SPRINT 15.1 MCP DISCOVERY SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
