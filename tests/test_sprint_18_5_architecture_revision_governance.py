from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_revision_service import ArchitectureRevisionService
from services.capability_registry_service import CapabilityRegistryService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        session_id="session-18-5",
        agent_id="lex",
        project_id=project_id,
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )


def _seed(tmp_path: Path) -> tuple[ArchitectureRegistryService, str]:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project", description="Project root.")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Architecture domain.")
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Revision Governance", node_key="RevisionGovernance", parent_id=domain.architecture_id, node_type="component", description="Initial architecture revision governance component.")
    return service, component.architecture_id


def _revision_proposal(tmp_path: Path, architecture_id: str, description: str = "Approved governed description."):
    return ArchitectureRegistryService(tmp_path).propose_revision(
        project_id="Ageix_Test",
        architecture_id_or_path=architecture_id,
        submitted_by="lex",
        provider="openai",
        objective="Approve governed architecture revision.",
        proposed_changes={
            "description": description,
            "metadata": {"governance_sprint": "18.5"},
            "evidence_links": ["EVPKG-ARCHITECTURE-NAPKIN"],
        },
        metadata={"session_id": "session-18-5"},
    )


def _approve(tmp_path: Path, proposal_id: str) -> str:
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(tmp_path).create_trace(
        decision_summary="Chair approved architecture revision governance update.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "session-18-5"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Evidence was sufficient for architecture baseline evolution.",
    )
    return trace.trace_id


def test_approved_revision_creates_immutable_snapshot_and_active_baseline(tmp_path: Path) -> None:
    _, architecture_id = _seed(tmp_path)
    proposed = _revision_proposal(tmp_path, architecture_id)
    trace_id = _approve(tmp_path, proposed.linked_proposal_id or "")

    revision = ArchitectureRevisionService(tmp_path).apply_approved_revision(
        revision_proposal_id=proposed.revision_id,
        approved_by="chair",
        revision_type="create",
        decision_trace_id=trace_id,
    )

    baseline = ArchitectureRevisionService(tmp_path).get_current_baseline(architecture_id=architecture_id)
    details = ArchitectureRevisionService(tmp_path).get_revision(revision.revision_id, include_snapshot=True)
    node = ArchitectureRegistryService(tmp_path).require_node(architecture_id)

    assert revision.revision_id.startswith("ARCHRVSN-")
    assert revision.snapshot_id.startswith("ARCHSNAP-")
    assert revision.baseline_version == "v1"
    assert revision.decision_trace_id == trace_id
    assert baseline.active_revision_id == revision.revision_id
    assert baseline.active_version == "v1"
    assert details["snapshot"]["root"]["root_id"] == architecture_id
    assert node.description == "Approved governed description."
    assert "EVPKG-ARCHITECTURE-NAPKIN" in node.linked_evidence_package_ids


def test_unapproved_proposal_cannot_create_architecture_revision(tmp_path: Path) -> None:
    _, architecture_id = _seed(tmp_path)
    proposed = _revision_proposal(tmp_path, architecture_id)

    try:
        ArchitectureRevisionService(tmp_path).apply_approved_revision(
            revision_proposal_id=proposed.revision_id,
            approved_by="chair",
        )
    except PermissionError as exc:
        assert str(exc) == "approved_architecture_proposal_required"
    else:
        raise AssertionError("unapproved proposals must not create architecture revisions")

    assert ArchitectureRevisionService(tmp_path).get_current_baseline(architecture_id=architecture_id, required=False) is None


def test_second_revision_supersedes_previous_revision_and_preserves_history(tmp_path: Path) -> None:
    _, architecture_id = _seed(tmp_path)
    first_proposal = _revision_proposal(tmp_path, architecture_id, "First approved baseline.")
    _approve(tmp_path, first_proposal.linked_proposal_id or "")
    first = ArchitectureRevisionService(tmp_path).apply_approved_revision(revision_proposal_id=first_proposal.revision_id, approved_by="chair", revision_type="create")

    second_proposal = _revision_proposal(tmp_path, architecture_id, "Second approved baseline.")
    _approve(tmp_path, second_proposal.linked_proposal_id or "")
    second = ArchitectureRevisionService(tmp_path).apply_approved_revision(revision_proposal_id=second_proposal.revision_id, approved_by="chair")

    history = ArchitectureRevisionService(tmp_path).get_history(architecture_id=architecture_id)
    first_details = ArchitectureRevisionService(tmp_path).get_revision(first.revision_id)

    assert second.baseline_version == "v2"
    assert second.supersedes_revision_id == first.revision_id
    assert first_details["status"] == "superseded"
    assert history["current_baseline"]["active_revision_id"] == second.revision_id
    assert [item["baseline_version"] for item in history["revisions"]] == ["v1", "v2"]
    assert history["immutable_history"] is True


def test_revision_read_capabilities_are_registered_and_mcp_exposed(tmp_path: Path) -> None:
    _, architecture_id = _seed(tmp_path)
    registry = CapabilityRegistryService(tmp_path)
    for capability_id in {
        "architecture.revisions",
        "architecture.revision.details",
        "architecture.history",
        "architecture.baseline.current",
    }:
        assert registry.exists(capability_id)

    proposed = _revision_proposal(tmp_path, architecture_id)
    _approve(tmp_path, proposed.linked_proposal_id or "")
    revision = ArchitectureRevisionService(tmp_path).apply_approved_revision(revision_proposal_id=proposed.revision_id, approved_by="chair")

    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    assert "ageix.architecture.revisions" in tools
    assert "ageix.architecture.revision.details" in tools
    assert "ageix.architecture.history" in tools
    assert "ageix.architecture.baseline.current" in tools

    baseline = facade.execute_tool("ageix.architecture.baseline.current", _context(), {"architecture_id": architecture_id})
    history = facade.execute_tool("ageix.architecture.history", _context(), {"architecture_id": architecture_id})
    details = facade.execute_tool("ageix.architecture.revision.details", _context(), {"revision_id": revision.revision_id, "include_snapshot": True})

    assert baseline.success is True
    assert baseline.result["baseline"]["active_revision_id"] == revision.revision_id
    assert history.success is True
    assert history.result["count"] == 1
    assert details.success is True
    assert details.result["snapshot"]["snapshot_id"] == revision.snapshot_id
