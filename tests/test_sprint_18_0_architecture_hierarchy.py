from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_registry_service import ArchitectureRegistryService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixRequestContext


def test_architecture_registry_persists_parent_child_hierarchy(tmp_path: Path) -> None:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Evidence", node_key="Evidence", parent_id=project.architecture_id, node_type="domain")
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Evidence Broker", node_key="EvidenceBroker", parent_id=domain.architecture_id, node_type="component")

    reloaded = ArchitectureRegistryService(tmp_path)
    assert reloaded.require_node("AgeixTest.Evidence.EvidenceBroker").architecture_id == component.architecture_id
    children = reloaded.get_children(domain.architecture_id)
    assert [child["architecture_id"] for child in children["children"]] == [component.architecture_id]
    assert reloaded.require_node(project.architecture_id).path == "AgeixTest"


def test_architecture_registry_links_evidence_and_decisions(tmp_path: Path) -> None:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Governance", node_key="Governance", parent_id=project.architecture_id, node_type="domain")

    updated = service.link_evidence(domain.architecture_id, ["EVPKG-ONE", "EVPKG-ONE"], ["TRACE-ONE"])

    assert updated.linked_evidence_package_ids == ["EVPKG-ONE"]
    assert updated.linked_decision_trace_ids == ["TRACE-ONE"]
    assert updated.health.linked_evidence_count == 1
    assert updated.health.linked_decision_count == 1
    index_entry = service.list_nodes(project_id="Ageix_Test", node_type="domain")["nodes"][0]
    assert index_entry["linked_evidence_count"] == 1
    assert index_entry["linked_decision_count"] == 1


def test_architecture_subtree_retrieval(tmp_path: Path) -> None:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="MCP Platform", node_key="MCPPlatform", parent_id=project.architecture_id, node_type="domain")
    service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Tool Registry", node_key="ToolRegistry", parent_id=domain.architecture_id, node_type="component")

    subtree = service.get_subtree("AgeixTest.MCPPlatform")

    assert subtree["root_id"] == domain.architecture_id
    assert subtree["subtree"]["node"]["name"] == "MCP Platform"
    assert subtree["subtree"]["children"][0]["node"]["path"] == "AgeixTest.MCPPlatform.ToolRegistry"


def test_architecture_reviewer_definitions_are_seeded(tmp_path: Path) -> None:
    reviewers = ArchitectureRegistryService(tmp_path).ensure_reviewers()

    lex = next(item for item in reviewers["reviewers"] if item["reviewer_id"] == "lex")
    claude = next(item for item in reviewers["reviewers"] if item["reviewer_id"] == "claude")
    assert lex["enabled"] is True
    assert lex["transport_mode"] == "mcp_contextual"
    assert claude["enabled"] is False
    assert claude["transport_mode"] == "api_packet"
    assert claude["can_directly_modify_architecture"] is False


def test_architecture_capabilities_are_registered_and_mcp_visible(tmp_path: Path) -> None:
    registry = CapabilityRegistryService(tmp_path)
    assert registry.exists("architecture.list")
    assert registry.exists("architecture.details")
    assert registry.exists("architecture.children")
    assert registry.exists("architecture.subtree")

    facade = MCPFacadeService(tmp_path)
    tools = facade.discover_tools(category="architecture")
    tool_names = {tool["tool_name"] for tool in tools}
    assert "ageix.architecture.list" in tool_names
    assert "ageix.architecture.details" in tool_names
    assert "ageix.architecture.children" in tool_names
    assert "ageix.architecture.subtree" in tool_names


def test_mcp_architecture_retrieval_is_governed_read_only(tmp_path: Path) -> None:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project")
    service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Evidence", node_key="Evidence", parent_id=project.architecture_id, node_type="domain")

    context = AgeixRequestContext(
        session_id="session-18-0",
        agent_id="lex",
        project_id="Ageix_Test",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(tmp_path)

    listed = facade.execute_tool("ageix.architecture.list", context, {"node_type": "domain"})
    assert listed.success is True
    assert listed.result["count"] == 1
    assert listed.governance["chair_authority_preserved"] is True

    details = facade.execute_tool("ageix.architecture.details", context, {"path": "AgeixTest.Evidence"})
    assert details.success is True
    assert details.result["node_type"] == "domain"


def test_official_ageix_architecture_seed(tmp_path: Path) -> None:
    service = ArchitectureRegistryService(tmp_path)
    result = service.seed_official_ageix_architecture()

    assert result["seeded"] is True
    domains = service.list_nodes(project_id="Ageix", node_type="domain")
    names = {node["name"] for node in domains["nodes"]}
    assert {"Governance", "Evidence", "Consultation", "MCP Platform", "Validation", "Architecture"}.issubset(names)
    evidence_children = service.get_children("Ageix.Evidence")
    assert "Evidence Packages" in {child["name"] for child in evidence_children["children"]}
