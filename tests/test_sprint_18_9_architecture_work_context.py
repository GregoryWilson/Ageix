from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_work_context_service import ArchitectureWorkContextService
from services.capability_registry_service import CapabilityRegistryService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(session_id="session-18-9", agent_id="lex", project_id=project_id, client_id="chatGPT", provider="chatGPT", authentication_method="dev_token")


def _seed(tmp_path: Path) -> tuple[str, str, str, str]:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project", description="Project root.")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Architecture domain.")
    impact = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-IMPACT", name="MCP Platform", node_key="McpPlatform", parent_id=project.architecture_id, node_type="domain", description="Impacted platform.")
    component = service.create_node(
        project_id="Ageix_Test",
        architecture_id="ARCH-COMPONENT",
        name="Work Context",
        node_key="WorkContext",
        parent_id=domain.architecture_id,
        node_type="component",
        description="Work context component.",
        metadata={"relationships": {"downstream": [impact.architecture_id]}, "open_considerations": ["Worker instructions remain future work."]},
    )
    return project.architecture_id, domain.architecture_id, component.architecture_id, impact.architecture_id


def _approve(tmp_path: Path, proposal_id: str) -> str:
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(tmp_path).create_trace(
        decision_summary="Chair approved sprint 18.9 architecture artifact.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "session-18-9"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Evidence was sufficient for work context maturity.",
    )
    return trace.trace_id


def _accept_principle(tmp_path: Path, **kwargs):
    service = ArchitectureGuidanceService(tmp_path)
    principle = service.propose_principle(project_id="Ageix_Test", session_id="session-18-9", created_by="lex", **kwargs)
    trace = _approve(tmp_path, principle.proposal_id)
    return service.accept_approved_principle(principle.principle_id, approved_by="chair", decision_trace_id=trace)


def _accept_intent(tmp_path: Path, **kwargs):
    service = ArchitectureGuidanceService(tmp_path)
    intent = service.propose_intent(project_id="Ageix_Test", session_id="session-18-9", created_by="lex", **kwargs)
    trace = _approve(tmp_path, intent.proposal_id)
    return service.accept_approved_intent(intent.intent_id, approved_by="chair", decision_trace_id=trace)


def test_work_context_is_summary_first_traceable_and_impact_aware(tmp_path: Path) -> None:
    project_id, domain_id, component_id, impact_id = _seed(tmp_path)
    project_principle = _accept_principle(tmp_path, title="Governed work", statement="Work context must preserve architecture governance.", architecture_ids=[project_id], evidence_package_ids=["EVPKG-WORK"])
    component_intent = _accept_intent(tmp_path, title="Work analysis", summary="Work context should bridge guidance and future workers without generating instructions.", architecture_ids=[component_id], future_considerations=["Worker instruction generation may follow later."])

    package = ArchitectureWorkContextService(tmp_path).build_work_context_package(
        architecture_id=component_id,
        work_summary="Add architecture-aware worker context retrieval.",
        persist=True,
    )

    assert package.work_context_id.startswith("WORKCTX-")
    assert package.persisted_snapshot is True
    assert package.summary_first is True
    assert package.generated_on_demand is False
    assert package.affected_scope["architecture_ids"] == [component_id]
    assert package.resolved_architecture_nodes[0]["architecture_id"] == component_id
    assert package.guidance_context["package_count"] == 1
    assert package.governing_principles[0]["principle_id"] == project_principle.principle_id
    assert package.active_intent[0]["intent_id"] == component_intent.intent_id
    assert {item["architecture_id"] for item in package.impacted_nodes} == {domain_id, impact_id}
    assert package.relationship_summary["traversal"] == "direct_only"
    assert package.relationship_summary["max_depth"] == 1
    assert any(item.get("proposal_id") == project_principle.proposal_id for item in package.traceability)
    assert package.metadata["no_worker_instruction_generation"] is True

    persisted = ArchitectureWorkContextService(tmp_path).get_package(package.work_context_id)
    assert persisted["work_context_id"] == package.work_context_id


def test_work_context_resolves_multiple_nodes_and_exact_scope_inputs(tmp_path: Path) -> None:
    _, domain_id, component_id, impact_id = _seed(tmp_path)
    principle = _accept_principle(tmp_path, title="Exact scope", statement="Exact deterministic scope inputs resolve work context.", architecture_ids=[domain_id])
    intent = _accept_intent(tmp_path, title="Exact intent", summary="Intent-linked work context resolves deterministically.", architecture_ids=[component_id])
    svc = ArchitectureWorkContextService(tmp_path)

    assert svc.build_work_context_package(path="AgeixTest.Architecture.WorkContext").resolved_architecture_nodes[0]["architecture_id"] == component_id
    assert svc.build_work_context_package(node_key="WorkContext", project_id="Ageix_Test").resolved_architecture_nodes[0]["architecture_id"] == component_id
    assert svc.build_work_context_package(name="Work Context", project_id="Ageix_Test").resolved_architecture_nodes[0]["architecture_id"] == component_id
    assert svc.build_work_context_package(principle_id=principle.principle_id).resolved_architecture_nodes[0]["architecture_id"] == domain_id
    assert svc.build_work_context_package(intent_id=intent.intent_id).resolved_architecture_nodes[0]["architecture_id"] == component_id

    multi = svc.build_work_context_package(architecture_ids=[component_id, impact_id])
    assert multi.affected_scope["multi_node"] is True
    assert multi.affected_scope["count"] == 2


def test_work_context_rejects_unresolved_scope_and_recursive_impact(tmp_path: Path) -> None:
    _seed(tmp_path)
    svc = ArchitectureWorkContextService(tmp_path)

    try:
        svc.build_work_context_package(work_summary="Free-form text only should not resolve.")
    except ValueError as exc:
        assert str(exc) == "architecture_work_scope_not_resolved"
    else:
        raise AssertionError("free-form scope unexpectedly resolved")

    try:
        svc.build_work_context_package(architecture_id="ARCH-COMPONENT", max_depth=2)
    except ValueError as exc:
        assert str(exc) == "architecture_work_context_supports_direct_relationships_only"
    else:
        raise AssertionError("recursive impact unexpectedly accepted")


def test_mcp_work_context_is_exposed_and_retrievable(tmp_path: Path) -> None:
    _, _, component_id, _ = _seed(tmp_path)
    _accept_principle(tmp_path, title="MCP work", statement="MCP consumers can retrieve architecture-aware work context.", architecture_ids=[component_id])

    registry = CapabilityRegistryService(tmp_path)
    assert registry.exists("architecture.work.context")
    assert registry.exists("architecture.work.context.get")

    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.work.context" in tools
    assert "ageix.architecture.work.context.get" in tools

    filtered = facade.execute_tool("ageix.capabilities.list", _context(), {"category": "architecture", "query": "work.context", "limit": 10, "offset": 0})
    assert filtered.success is True
    assert {tool["tool_name"] for tool in filtered.result["tools"]} >= {"ageix.architecture.work.context", "ageix.architecture.work.context.get"}

    generated = facade.execute_tool("ageix.architecture.work.context", _context(), {"architecture_id": component_id, "work_summary": "Retrieve work context."})
    persisted = facade.execute_tool("ageix.architecture.work.context", _context(), {"architecture_id": component_id, "persist": True, "persist_guidance_context": True})
    fetched = facade.execute_tool("ageix.architecture.work.context.get", _context(), {"work_context_id": persisted.result["work_context_id"]})

    assert generated.success is True
    assert generated.result["persisted_snapshot"] is False
    assert persisted.success is True
    assert persisted.result["work_context_id"].startswith("WORKCTX-")
    assert persisted.result["guidance_context_package_ids"][0].startswith("GUIDECTX-")
    assert fetched.success is True
    assert fetched.result["work_context_id"] == persisted.result["work_context_id"]


def test_smoke_cleanup_removes_only_work_context_package(tmp_path: Path) -> None:
    _, _, component_id, _ = _seed(tmp_path)
    package = ArchitectureWorkContextService(tmp_path).build_work_context_package(architecture_id=component_id, persist=True)
    ArchitectureWorkContextService(tmp_path).cleanup_package(package.work_context_id)

    assert not (tmp_path / ".ageix" / "architecture" / "work_context" / package.work_context_id).exists()
    assert ArchitectureRegistryService(tmp_path).require_node(component_id).architecture_id == component_id
