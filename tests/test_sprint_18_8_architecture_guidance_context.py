from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_context_service import ArchitectureContextService
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_revision_service import ArchitectureRevisionService
from services.capability_registry_service import CapabilityRegistryService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(session_id="session-18-8", agent_id="lex", project_id=project_id, client_id="chatGPT", provider="chatGPT", authentication_method="dev_token")


def _seed(tmp_path: Path) -> tuple[str, str, str]:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project", description="Project root.")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Architecture domain.")
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Guidance Context", node_key="GuidanceContext", parent_id=domain.architecture_id, node_type="component", description="Guidance context component.", metadata={"open_considerations": ["Worker context packaging remains future work."]})
    return project.architecture_id, domain.architecture_id, component.architecture_id


def _approve(tmp_path: Path, proposal_id: str) -> str:
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(tmp_path).create_trace(
        decision_summary="Chair approved sprint 18.8 architecture artifact.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "session-18-8"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Evidence was sufficient for guidance context maturity.",
    )
    return trace.trace_id


def _accept_principle(tmp_path: Path, **kwargs):
    service = ArchitectureGuidanceService(tmp_path)
    principle = service.propose_principle(project_id="Ageix_Test", session_id="session-18-8", created_by="lex", **kwargs)
    trace = _approve(tmp_path, principle.proposal_id)
    return service.accept_approved_principle(principle.principle_id, approved_by="chair", decision_trace_id=trace)


def _accept_intent(tmp_path: Path, **kwargs):
    service = ArchitectureGuidanceService(tmp_path)
    intent = service.propose_intent(project_id="Ageix_Test", session_id="session-18-8", created_by="lex", **kwargs)
    trace = _approve(tmp_path, intent.proposal_id)
    return service.accept_approved_intent(intent.intent_id, approved_by="chair", decision_trace_id=trace)


def _accepted_adr(tmp_path: Path, architecture_id: str):
    service = ArchitectureDecisionRecordService(tmp_path)
    adr = service.propose_adr(
        project_id="Ageix_Test",
        session_id="session-18-8",
        created_by="lex",
        title="Guidance context packages",
        context="Architecture guidance needs concise retrieval context.",
        decision="Create first-class summary-first guidance context packages.",
        rationale="Workers and MCP consumers need scoped architectural context without oversized payloads.",
        architecture_ids=[architecture_id],
        future_considerations=["Architecture Work Context may consume guidance context packages."],
        evidence_package_ids=[],
    )
    trace = _approve(tmp_path, adr.proposal_id)
    return service.accept_approved_adr(adr.adr_id, approved_by="chair", decision_trace_id=trace)


def _revision(tmp_path: Path, architecture_id: str, description: str):
    proposed = ArchitectureRegistryService(tmp_path).propose_revision(
        project_id="Ageix_Test",
        architecture_id_or_path=architecture_id,
        submitted_by="lex",
        objective="Approve guidance context baseline.",
        proposed_changes={"description": description, "evidence_links": ["EVPKG-18-8"]},
        metadata={"session_id": "session-18-8"},
    )
    trace = _approve(tmp_path, proposed.linked_proposal_id or "")
    return ArchitectureRevisionService(tmp_path).apply_approved_revision(revision_proposal_id=proposed.revision_id, approved_by="chair", decision_trace_id=trace)


def test_guidance_context_package_is_summary_first_effective_and_traceable(tmp_path: Path) -> None:
    project_id, domain_id, component_id = _seed(tmp_path)
    project_principle = _accept_principle(tmp_path, title="Governed context", statement="Architecture guidance context must preserve governance lineage.", architecture_ids=[project_id], evidence_package_ids=["EVPKG-ROOT"])
    domain_principle = _accept_principle(tmp_path, title="Scoped retrieval", statement="Guidance retrieval must be scoped and summary-first.", architecture_ids=[domain_id], metadata={"conflicts_with_principle_ids": [project_principle.principle_id]})
    component_intent = _accept_intent(tmp_path, title="Worker-ready guidance", summary="Guidance context should prepare for future worker context without generating worker instructions.", architecture_ids=[component_id], principle_ids=[domain_principle.principle_id], future_considerations=["Architecture Work Context may be introduced in 18.9."], metadata={"open_considerations": ["Worker instruction generation remains out of scope."]})
    adr = _accepted_adr(tmp_path, domain_id)
    # Link the ADR to existing guidance records after acceptance through existing immutable-write pattern.
    domain_principle.adr_ids.append(adr.adr_id)
    component_intent.adr_ids.append(adr.adr_id)
    ArchitectureGuidanceService(tmp_path)._write_principle(domain_principle)
    ArchitectureGuidanceService(tmp_path)._write_intent(component_intent)
    first = _revision(tmp_path, component_id, "First guidance context baseline.")
    second = _revision(tmp_path, component_id, "Second guidance context baseline.")

    package = ArchitectureGuidanceContextService(tmp_path).build_context_package(architecture_id=component_id, persist=True)

    assert package.package_id.startswith("GUIDECTX-")
    assert package.persisted_snapshot is True
    assert package.summary_first is True
    assert package.immutable_snapshot is True
    assert package.brief_summary.startswith("Guidance context for Guidance Context")
    assert [item["principle_id"] for item in package.governing_principles][:2] == [domain_principle.principle_id, project_principle.principle_id]
    assert package.active_intent[0]["intent_id"] == component_intent.intent_id
    assert package.decision_context[0]["adr_id"] == adr.adr_id
    assert package.source_revision_id == second.revision_id
    assert [item["revision_id"] for item in package.revision_lineage] == [first.revision_id, second.revision_id]
    assert package.conflicts[0]["resolution"] == "exposed_not_resolved"
    assert any(item.get("proposal_id") == domain_principle.proposal_id and item.get("summary") for item in package.traceability)
    assert package.architecture_scope["architecture_id"] == component_id
    assert [item["architecture_id"] for item in package.affected_nodes] == [component_id, domain_id, project_id]

    persisted = ArchitectureGuidanceContextService(tmp_path).get_package(package.package_id)
    assert persisted["package_id"] == package.package_id


def test_scoped_retrieval_by_principle_intent_adr_revision_and_path(tmp_path: Path) -> None:
    _, domain_id, component_id = _seed(tmp_path)
    principle = _accept_principle(tmp_path, title="Explicit scope", statement="Explicit scopes resolve to their architecture node.", architecture_ids=[domain_id])
    intent = _accept_intent(tmp_path, title="Intent scope", summary="Intent scopes resolve deterministically.", architecture_ids=[component_id])
    adr = _accepted_adr(tmp_path, domain_id)
    revision = _revision(tmp_path, component_id, "Scoped revision baseline.")
    svc = ArchitectureGuidanceContextService(tmp_path)

    assert svc.build_context_package(path="AgeixTest.Architecture.GuidanceContext").architecture_id == component_id
    assert svc.build_context_package(principle_id=principle.principle_id).architecture_id == domain_id
    assert svc.build_context_package(intent_id=intent.intent_id).architecture_id == component_id
    assert svc.build_context_package(adr_id=adr.adr_id).architecture_id == domain_id
    assert svc.build_context_package(revision_id=revision.revision_id).architecture_id == component_id


def test_architecture_context_contains_lightweight_guidance_summary_with_drilldown(tmp_path: Path) -> None:
    _, _, component_id = _seed(tmp_path)
    _accept_principle(tmp_path, title="Lightweight context", statement="Architecture context should include only lightweight guidance summary.", architecture_ids=[component_id])
    context = ArchitectureContextService(tmp_path).build_context(component_id)

    assert context.guidance["guidance_summary"]["detail_available"] is True
    assert context.guidance["guidance_summary"]["detail_path"]["tool"] == "architecture.guidance.context"
    assert context.context_policy["active_guidance_included"] is True


def test_mcp_guidance_context_and_capability_filtering_are_exposed(tmp_path: Path) -> None:
    _, _, component_id = _seed(tmp_path)
    _accept_principle(tmp_path, title="MCP context", statement="MCP consumers can retrieve only relevant guidance context.", architecture_ids=[component_id])

    registry = CapabilityRegistryService(tmp_path)
    assert registry.exists("architecture.guidance.context")
    assert registry.exists("architecture.guidance.context.get")

    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.guidance.context" in tools

    filtered = facade.execute_tool("ageix.capabilities.list", _context(), {"category": "architecture", "query": "guidance", "limit": 5, "offset": 0})
    assert filtered.success is True
    assert filtered.result["filters"] == {"category": "architecture", "query": "guidance"}
    assert filtered.result["count"] <= 5
    assert all("guidance" in (tool["tool_name"] + tool.get("description", "")).lower() for tool in filtered.result["tools"])

    generated = facade.execute_tool("ageix.architecture.guidance.context", _context(), {"architecture_id": component_id})
    persisted = facade.execute_tool("ageix.architecture.guidance.context", _context(), {"architecture_id": component_id, "persist": True})
    fetched = facade.execute_tool("ageix.architecture.guidance.context.get", _context(), {"package_id": persisted.result["package_id"]})

    assert generated.success is True
    assert generated.result["persisted_snapshot"] is False
    assert persisted.success is True
    assert persisted.result["package_id"].startswith("GUIDECTX-")
    assert fetched.success is True
    assert fetched.result["package_id"] == persisted.result["package_id"]


def test_smoke_cleanup_removes_only_guidance_context_package(tmp_path: Path) -> None:
    _, _, component_id = _seed(tmp_path)
    package = ArchitectureGuidanceContextService(tmp_path).build_context_package(architecture_id=component_id, persist=True)
    ArchitectureGuidanceContextService(tmp_path).cleanup_package(package.package_id)

    assert not (tmp_path / ".ageix" / "architecture" / "guidance_context" / package.package_id).exists()
    assert ArchitectureRegistryService(tmp_path).require_node(component_id).architecture_id == component_id
