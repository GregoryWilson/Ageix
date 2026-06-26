from __future__ import annotations

import json
from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_context_service import ArchitectureContextService
from services.architecture_registry_service import ArchitectureRegistryService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixRequestContext


def _seed_node(tmp_path: Path) -> tuple[ArchitectureRegistryService, str]:
    registry = ArchitectureRegistryService(tmp_path)
    project = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project")
    domain = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-EVIDENCE", name="Evidence", node_key="Evidence", parent_id=project.architecture_id, node_type="domain", description="Evidence domain.")
    component = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-BROKER", name="Evidence Broker", node_key="EvidenceBroker", parent_id=domain.architecture_id, node_type="component", description="Governed evidence package creation and retrieval.", linked_evidence_package_ids=["EVPKG-ONE"], linked_decision_trace_ids=["TRACE-ONE"])
    return registry, component.architecture_id


def _seed_evidence_and_decision_indexes(tmp_path: Path) -> None:
    evidence_root = tmp_path / ".ageix" / "evidence_packages"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "index.json").write_text(json.dumps({"packages": [{
        "package_id": "EVPKG-ONE",
        "project_id": "Ageix_Test",
        "objective": "Evidence Broker architecture support",
        "proposal_id": "EAP-ONE",
        "evidence_plan_id": "EVP-ONE",
        "freshness_status": "unchanged",
        "stale": False,
        "primary_count": 2,
        "supporting_count": 3,
        "validation_count": 1,
        "governance": {"status": "active"},
    }]}, indent=2), encoding="utf-8")
    decision_root = tmp_path / ".ageix" / "decision_traces"
    decision_root.mkdir(parents=True, exist_ok=True)
    (decision_root / "index.json").write_text(json.dumps({"traces": [{
        "trace_id": "TRACE-ONE",
        "project_id": "Ageix_Test",
        "decision_id": "DEC-ONE",
        "decision_type": "architecture",
        "decision_summary": "Approve Evidence Broker as owner of governed package access.",
        "outcome": "approved",
        "proposal_id": "PROP-ONE",
        "evidence_package_ids": ["EVPKG-ONE"],
        "created_at": "2026-06-23T00:00:00+00:00",
    }]}, indent=2), encoding="utf-8")


def test_architecture_description_is_separate_versioned_artifact(tmp_path: Path) -> None:
    _, architecture_id = _seed_node(tmp_path)
    service = ArchitectureContextService(tmp_path)

    draft = service.create_description(
        architecture_id,
        purpose="Provide governed evidence context to workers and external agents.",
        responsibilities=["Plan evidence access", "Persist immutable packages"],
        boundaries=["Does not make Chair decisions"],
        open_questions=["Future service/file mapping deferred"],
        detailed_description="Detailed architecture narrative can be longer than summary context.",
    )
    approved = service.approve_description(draft.description_id, approved_by="chair")

    assert approved.version == 1
    assert approved.state == "approved"
    assert service.active_description_for_node(architecture_id).description_id == approved.description_id
    entries = service.list_descriptions(architecture_id)["descriptions"]
    assert entries[0]["description_id"] == approved.description_id


def test_architecture_context_is_summary_first_and_links_evidence_not_contents(tmp_path: Path) -> None:
    _, architecture_id = _seed_node(tmp_path)
    _seed_evidence_and_decision_indexes(tmp_path)
    service = ArchitectureContextService(tmp_path)
    service.approve_description(service.create_description(
        architecture_id,
        purpose="Provide governed evidence context.",
        responsibilities=["Plan evidence", "Retrieve packages"],
        boundaries=["Does not own evidence contents"],
        detailed_description="Full description detail.",
    ).description_id)

    context = service.build_context("AgeixTest.Evidence.EvidenceBroker")

    assert context.summary.startswith("AgeixTest.Evidence.EvidenceBroker")
    assert context.context_policy["summary_first"] is True
    assert context.context_policy["repository_wide_discovery_performed"] is False
    assert context.context_policy["evidence_is_linked_not_absorbed"] is True
    assert context.linked_evidence_summary[0]["package_id"] == "EVPKG-ONE"
    assert context.linked_evidence_summary[0]["objective"] == "Evidence Broker architecture support"
    assert "contents" not in context.linked_evidence_summary[0]
    assert context.linked_decision_summary[0]["decision_id"] == "DEC-ONE"
    assert context.detail == {}


def test_architecture_context_detail_is_opt_in(tmp_path: Path) -> None:
    _, architecture_id = _seed_node(tmp_path)
    service = ArchitectureContextService(tmp_path)
    draft = service.create_description(architecture_id, purpose="Purpose", detailed_description="Long form detail")
    service.approve_description(draft.description_id)

    context = service.build_context(architecture_id, include_detail=True)

    assert context.detail_available is True
    assert context.detail["node"]["architecture_id"] == architecture_id
    assert context.detail["description"]["detailed_description"] == "Long form detail"
    assert context.detail["evidence_link_policy"].startswith("Architecture links")


def test_architecture_context_capability_is_registered_and_mcp_visible(tmp_path: Path) -> None:
    capability_registry = CapabilityRegistryService(tmp_path)
    assert capability_registry.exists("architecture.context")

    facade = MCPFacadeService(tmp_path)
    tools = facade.discover_tools(category="architecture")
    names = {tool["tool_name"] for tool in tools}
    assert "ageix.architecture.context" in names


def test_mcp_architecture_context_execution_preserves_governance(tmp_path: Path) -> None:
    _, architecture_id = _seed_node(tmp_path)
    service = ArchitectureContextService(tmp_path)
    service.approve_description(service.create_description(architecture_id, purpose="MCP context purpose").description_id)
    context = AgeixRequestContext(
        session_id="session-18-1",
        agent_id="lex",
        project_id="Ageix_Test",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )

    response = MCPFacadeService(tmp_path).execute_tool("ageix.architecture.context", context, {"path": "AgeixTest.Evidence.EvidenceBroker"})

    assert response.success is True
    assert response.result["purpose"] == "MCP context purpose"
    assert response.result["context_policy"]["summary_first"] is True
    assert response.governance["chair_authority_preserved"] is True


def test_non_external_description_write_capabilities_do_not_surface_to_mcp_discovery(tmp_path: Path) -> None:
    registry = CapabilityRegistryService(tmp_path)
    assert registry.exists("architecture.description.draft")
    assert registry.exists("architecture.description.approve")

    facade = MCPFacadeService(tmp_path)
    names = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.context" in names
    assert "ageix.architecture.description.draft" not in names
    assert "ageix.architecture.description.approve" not in names
