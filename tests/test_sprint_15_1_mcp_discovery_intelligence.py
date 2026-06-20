from __future__ import annotations

from pathlib import Path

from mcp.discovery_service import DISCOVERY_SCHEMA_VERSION, MCPDiscoveryService
from mcp.facade_service import MCPFacadeService
from mcp.tool_definitions import MCPToolDefinition
from mcp.tool_registry import MCPToolRegistry
from models.capability_definition import CapabilityDefinition
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService


def _tool(service: MCPFacadeService, name: str) -> dict:
    return next(item for item in service.discover_tools() if item["tool_name"] == name)


def _seed_project(tmp_path: Path, project_id: str = "Ageix_Test") -> None:
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="sprint-15-1-session",
        project_id=project_id,
    )


def test_mcp_discovery_metadata(tmp_path: Path):
    service = MCPFacadeService(tmp_path)
    tool = _tool(service, "ageix.proposals.submit")

    assert tool["discovery_schema_version"] == DISCOVERY_SCHEMA_VERSION
    assert tool["category"] == "proposal"
    assert tool["access_level"] == "governed_read"
    assert tool["requires_project"] is True
    assert tool["requires_auth"] is True
    assert tool["requires_proposal"] is True
    assert tool["exposed_to_external_agents"] is True
    assert tool["metadata_ready_for_documentation"] is True


def test_mcp_input_schema_exposure(tmp_path: Path):
    tool = _tool(MCPFacadeService(tmp_path), "ageix.proposals.submit")
    schema = tool["input_schema"]

    assert schema["type"] == "object"
    assert "objective" in schema["required"]
    assert schema["properties"]["objective"]["type"] == "string"
    assert "architecture" in schema["properties"]["proposal_type"]["enum"]


def test_mcp_capability_metadata_mapping(tmp_path: Path):
    service = MCPFacadeService(tmp_path)
    health = _tool(service, "ageix.health")

    assert health["access_level"] == "read"
    assert health["capability_category"] == "system"
    assert health["capability_handler"] == "system.health"
    assert health["capability_description"] == "Return Ageix capability interface health."


def test_mcp_discovery_filtering(tmp_path: Path):
    service = MCPFacadeService(tmp_path)

    proposal_tools = service.discover_tools(category="proposal")
    assert proposal_tools
    assert {tool["category"] for tool in proposal_tools} == {"proposal"}

    non_experimental = service.discover_tools(experimental=False)
    assert non_experimental
    assert all(tool["experimental"] is False for tool in non_experimental)

    without_placeholders = service.discover_tools(include_placeholders=False)
    assert without_placeholders
    assert all(tool["placeholder"] is False for tool in without_placeholders)
    assert "ageix.validation.scenario.request" not in {tool["tool_name"] for tool in without_placeholders}


def test_mcp_discovery_categories(tmp_path: Path):
    categories = MCPFacadeService(tmp_path).discover_categories()
    category_names = {item["category"] for item in categories}

    assert "system" in category_names
    assert "proposal" in category_names
    assert "consultation" in category_names
    assert "validation" in category_names
    assert all(item["discovery_schema_version"] == DISCOVERY_SCHEMA_VERSION for item in categories)


def test_mcp_discovery_relationships(tmp_path: Path):
    proposal = _tool(MCPFacadeService(tmp_path), "ageix.proposals.submit")
    validation = _tool(MCPFacadeService(tmp_path), "ageix.validation.scenario.request")

    assert "ageix.consultations.submit" in proposal["workflow"]["recommended_next_tools"]
    assert "ageix.proposals.status" in proposal["recommended_next_tools"]
    assert "ageix.validation.result.get" in validation["workflow"]["recommended_next_tools"]


def test_mcp_discovery_versioning(tmp_path: Path):
    tool = _tool(MCPFacadeService(tmp_path), "ageix.health")

    assert tool["version"] == "1.0"
    assert tool["discovery_schema_version"] == "1.0"


def test_mcp_discovery_preserves_governance(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)
    discovered = _tool(service, "ageix.health")

    assert discovered["governance_boundary"]["discovery_only"] is True
    assert discovered["governance_boundary"]["grants_authority"] is False
    assert discovered["governance_boundary"]["chair_authority_preserved"] is True

    response = service.execute_tool("ageix.health", _context(), {})
    assert response.success is True
    assert response.governance["chair_authority_preserved"] is True


def test_mcp_discovery_hides_non_exposed_capabilities(tmp_path: Path):
    registry = MCPToolRegistry(definitions=[
        MCPToolDefinition(
            name="ageix.hidden.tool",
            capability_id="hidden.tool",
            category="hidden",
            description="Hidden tool should not be discoverable externally.",
        )
    ])
    capability_registry = CapabilityRegistryService(tmp_path)
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

    discovery = MCPDiscoveryService(registry, capability_registry)

    assert discovery.discover_tools() == []
    internal = discovery.discover_tools(exposed_only=False)
    assert len(internal) == 1
    assert internal[0]["exposed_to_external_agents"] is False
