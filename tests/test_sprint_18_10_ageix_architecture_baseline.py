from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.mcp_context import AgeixRequestContext
from services.ageix_architecture_baseline_service import AgeixArchitectureBaselineService
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_work_context_service import ArchitectureWorkContextService
from services.project_registry_service import ProjectRegistryService
from services.capability_registry_service import CapabilityRegistryService



def test_architecture_supports_service_level_nodes(tmp_path: Path) -> None:
    registry = ArchitectureRegistryService(tmp_path)
    project = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-P", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project")
    domain = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-D", name="Evidence", node_key="Evidence", parent_id=project.architecture_id, node_type="domain")
    component = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-C", name="Evidence Broker", node_key="EvidenceBroker", parent_id=domain.architecture_id, node_type="component")
    service = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-S", name="EvidencePackageService", node_key="EvidencePackageService", parent_id=component.architecture_id, node_type="service", description="Creates immutable evidence packages. It preserves package metadata and traceability for governed retrieval.")

    children = registry.get_children(component.architecture_id)

    assert service.node_type.value == "service"
    assert children["children"][0]["node_type"] == "service"
    assert registry.get_node("AgeixTest.Evidence.EvidenceBroker.EvidencePackageService") is not None


def test_18_10_populates_canonical_ageix_architecture_baseline(tmp_path: Path) -> None:
    ProjectRegistryService(tmp_path).ensure_official_ageix_project()
    result = AgeixArchitectureBaselineService(tmp_path).populate()
    registry = ArchitectureRegistryService(tmp_path)

    assert result["baseline_version"] == "18.10"
    assert result["total_node_count"] >= 70
    assert result["domain_count"] == 10
    assert result["component_count"] >= 40
    assert result["service_count"] >= 45
    assert result["principle_count"] >= 6
    assert result["intent_count"] >= 5
    assert result["adr_count"] >= 13
    assert result["validation"]["valid"] is True

    service = registry.require_node("Ageix.EvidencePlatform.EvidenceBroker.EvidenceBrokerService")
    assert service.node_type.value == "service"
    assert "prevents broad repository walks" in service.description

    component = registry.require_node("Ageix.ArchitecturePlatform.WorkContext")
    summaries = component.metadata["service_summaries"]
    assert summaries
    assert summaries[0]["name"] == "ArchitectureWorkContextService"


def test_18_10_relationships_support_work_context_impact(tmp_path: Path) -> None:
    AgeixArchitectureBaselineService(tmp_path).populate()
    work = ArchitectureWorkContextService(tmp_path).build_work_context_package(
        project_id="Ageix",
        path="Ageix.MCPPlatform.Discovery",
        work_summary="Modify MCP discovery filtering.",
    )

    impacted_paths = {item["path"] for item in work.impacted_nodes}

    assert work.resolved_architecture_nodes[0]["path"] == "Ageix.MCPPlatform.Discovery"
    assert "Ageix.MCPPlatform" in impacted_paths
    assert "Ageix.MCPPlatform.CapabilityRegistry" in impacted_paths
    assert work.guidance_context["package_count"] == 1


def test_18_10_guidance_context_uses_seeded_principles_intent_and_adrs(tmp_path: Path) -> None:
    AgeixArchitectureBaselineService(tmp_path).populate()
    package = ArchitectureGuidanceContextService(tmp_path).build_context_package(project_id="Ageix", path="Ageix.MCPPlatform")

    principle_titles = {item["title"] for item in package.governing_principles}
    intent_titles = {item["title"] for item in package.active_intent}
    adr_titles = {item["title"] for item in package.decision_context}

    assert "Secure external boundaries" in principle_titles
    assert "Summary-first retrieval" in principle_titles
    assert "Composable capability architecture" in intent_titles
    assert "OAuth/JWT identity model" in adr_titles
    assert package.traceability


def test_18_10_retrieval_probe_and_cautious_review(tmp_path: Path) -> None:
    service = AgeixArchitectureBaselineService(tmp_path)
    result = service.populate(include_review=True)
    probe = service.retrieval_probe()
    reviews = ArchitectureRegistryService(tmp_path).list_reviews(project_id="Ageix", architecture_id="ARCH-AGEIX-PROJECT")

    assert result["review_id"]
    assert reviews["count"] == 1
    assert reviews["reviews"][0]["no_findings"] is True
    assert reviews["reviews"][0]["metadata"]["no_quality_scoring"] is True
    assert probe["retrieval_usable"] is True
    assert probe["work_context_probe"]["resolved_node_count"] == 1


def test_18_10_mcp_hidden_baseline_capabilities(tmp_path: Path) -> None:
    facade = MCPFacadeService(tmp_path)
    registry = CapabilityRegistryService(tmp_path)

    assert registry.exists("architecture.ageix.baseline.populate")
    assert registry.exists("architecture.ageix.baseline.validate")
    assert registry.exists("architecture.ageix.baseline.probe")

    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.ageix.baseline.populate" not in tools

    service = AgeixArchitectureBaselineService(tmp_path)
    populated = service.populate(include_review=True)
    validated = service.validate()
    probed = service.retrieval_probe()

    assert populated["validation"]["valid"] is True
    assert validated["valid"] is True
    assert probed["retrieval_usable"] is True
