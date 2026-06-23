from __future__ import annotations

import json
from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_context_service import ArchitectureContextService
from services.architecture_registry_service import ArchitectureRegistryService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixRequestContext


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        session_id="session-18-2",
        agent_id="lex",
        project_id=project_id,
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )


def _seed(tmp_path: Path) -> tuple[ArchitectureRegistryService, str, str, str]:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project", description="Project root.")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Evidence", node_key="Evidence", parent_id=project.architecture_id, node_type="domain", description="Evidence domain.")
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Evidence Broker", node_key="EvidenceBroker", parent_id=domain.architecture_id, node_type="component", description="Evidence broker component.")
    return service, project.architecture_id, domain.architecture_id, component.architecture_id


def test_architecture_health_uses_deterministic_status_enums(tmp_path: Path) -> None:
    service, _, _, component_id = _seed(tmp_path)
    node = service.link_evidence(component_id, ["EVPKG-ONE"], ["TRACE-ONE"])
    node.last_reviewed_at = "2026-06-23T12:00:00+00:00"
    node.review_count = 1
    service.upsert_node(node)

    health = service.get_health(component_id)["health"]

    assert health["architecture_id"] == component_id
    assert health["hierarchy_status"] == "valid"
    assert health["description_status"] == "partial"
    assert health["evidence_status"] == "present"
    assert health["decision_status"] == "present"
    assert health["review_status"] == "reviewed"
    assert health["context_status"] == "available"
    assert health["registration_status"] == "registered"
    assert health["health_version"] == 1
    assert health["metadata"]["no_ai_scoring"] is True


def test_architecture_context_failure_does_not_invalidate_overall_health(tmp_path: Path, monkeypatch) -> None:
    service, _, _, component_id = _seed(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("context broken")

    monkeypatch.setattr(ArchitectureContextService, "build_context", boom)
    health = service.get_health(component_id)["health"]

    assert health["context_status"] == "failed"
    assert health["status"] in {"partial", "complete"}
    assert health["hierarchy_status"] == "valid"


def test_architecture_coverage_is_registry_only_with_discovery_hook(tmp_path: Path) -> None:
    service, *_ = _seed(tmp_path)

    coverage = service.get_coverage(project_id="Ageix_Test").model_dump(mode="json")

    assert coverage["known_domains"] == 1
    assert coverage["mapped_domains"] == 1
    assert coverage["known_components"] == 1
    assert coverage["mapped_components"] == 1
    assert coverage["coverage_status"] == "complete_current_state"
    assert coverage["discovery_status"] == "unknown"
    assert coverage["metadata"]["repository_wide_discovery_performed"] is False


def test_architecture_freshness_default_is_project_configurable_30_days(tmp_path: Path) -> None:
    service, _, _, component_id = _seed(tmp_path)
    node_path = tmp_path / ".ageix" / "architecture" / "nodes" / f"{component_id}.json"
    payload = json.loads(node_path.read_text(encoding="utf-8"))
    payload["updated_at"] = "2026-01-01T00:00:00+00:00"
    node_path.write_text(json.dumps(payload), encoding="utf-8")

    stale = service.get_health(component_id)["health"]
    assert stale["freshness_status"] == "stale"
    assert stale["metadata"]["freshness_days"] == 30

    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "architecture.json").write_text(json.dumps({"architecture_freshness_days_by_project": {"Ageix_Test": 1000}}), encoding="utf-8")

    fresh = service.get_health(component_id)["health"]
    assert fresh["freshness_status"] == "fresh"
    assert fresh["metadata"]["freshness_days"] == 1000


def test_architecture_health_and_coverage_capabilities_are_mcp_visible_and_executable(tmp_path: Path) -> None:
    service, _, _, component_id = _seed(tmp_path)
    registry = CapabilityRegistryService(tmp_path)
    assert registry.exists("architecture.health")
    assert registry.exists("architecture.coverage")

    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.health" in tools
    assert "ageix.architecture.coverage" in tools

    health = facade.execute_tool("ageix.architecture.health", _context(), {"architecture_id": component_id})
    coverage = facade.execute_tool("ageix.architecture.coverage", _context(), {"project_id": "Ageix_Test"})

    assert health.success is True
    assert health.result["health"]["architecture_id"] == component_id
    assert coverage.success is True
    assert coverage.result["coverage_status"] == "complete_current_state"
    assert coverage.governance["chair_authority_preserved"] is True


def test_official_ageix_baseline_v1_contains_architecture_health_component(tmp_path: Path) -> None:
    service = ArchitectureRegistryService(tmp_path)
    service.seed_official_ageix_architecture()

    node = service.require_node("Ageix.Architecture.ArchitectureHealth")
    coverage = service.get_coverage(project_id="Ageix")

    assert node.name == "Architecture Health"
    assert node.metadata["seeded_by"] == "sprint_18_2_baseline_v1"
    assert coverage.coverage_status == "complete_current_state"