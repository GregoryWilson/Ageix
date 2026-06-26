from __future__ import annotations

import json
from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_registry_service import ArchitectureRegistryService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context(project_id: str = "Ageix_Test", agent_id: str = "lex", provider: str = "openai") -> AgeixRequestContext:
    return AgeixRequestContext(
        session_id="session-18-3",
        agent_id=agent_id,
        project_id=project_id,
        client_id="chatgpt",
        provider=provider,
        authentication_method="dev_token",
    )


def _seed(tmp_path: Path) -> tuple[ArchitectureRegistryService, str]:
    service = ArchitectureRegistryService(tmp_path)
    project = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-PROJECT", name="Ageix Test", node_key="AgeixTest", path="AgeixTest", node_type="project", description="Project root.")
    domain = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-DOMAIN", name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Architecture domain.")
    component = service.create_node(project_id="Ageix_Test", architecture_id="ARCH-COMPONENT", name="Review", node_key="Review", parent_id=domain.architecture_id, node_type="component", description="Architecture review component.")
    return service, component.architecture_id


def test_authorized_lex_can_submit_review_without_findings_and_updates_review_metadata(tmp_path: Path) -> None:
    service, component_id = _seed(tmp_path)

    review = service.submit_review(
        architecture_id_or_path=component_id,
        reviewer_id="lex",
        provider="openai",
        project_id="Ageix_Test",
        summary="Reviewed with no findings.",
        no_findings=True,
    )

    node = service.require_node(component_id)
    assert review.review_id.startswith("ARCHREV-")
    assert review.no_findings is True
    assert review.finding_ids == []
    assert node.review_count == 1
    assert node.last_reviewed_at == review.created_at


def test_unapproved_reviewer_is_denied_even_when_authenticated(tmp_path: Path) -> None:
    service, component_id = _seed(tmp_path)

    try:
        service.submit_review(
            architecture_id_or_path=component_id,
            reviewer_id="claude",
            provider="anthropic",
            project_id="Ageix_Test",
            summary="Not authorized yet.",
        )
    except PermissionError as exc:
        assert str(exc) == "architecture_reviewer_not_authorized"
    else:
        raise AssertionError("disabled reviewer should be denied")


def test_finding_other_requires_explanation_and_links_to_review(tmp_path: Path) -> None:
    service, component_id = _seed(tmp_path)
    review = service.submit_review(architecture_id_or_path=component_id, reviewer_id="lex", provider="openai", project_id="Ageix_Test", summary="Review.")

    try:
        service.submit_finding(
            project_id="Ageix_Test",
            created_by="lex",
            provider="openai",
            review_id=review.review_id,
            affected_architecture_ids=[component_id],
            category="other",
            summary="Other concern.",
        )
    except ValueError as exc:
        assert str(exc) == "other_explanation_required"
    else:
        raise AssertionError("other category without explanation should fail")

    finding = service.submit_finding(
        project_id="Ageix_Test",
        created_by="lex",
        provider="openai",
        review_id=review.review_id,
        affected_architecture_ids=[component_id],
        category="intent_miss",
        severity="significant_concern",
        summary="Intent was missed.",
        rationale="The baseline does not reflect the intended collaboration path.",
    )

    updated_review = service.get_review(review.review_id)
    assert finding.finding_id in updated_review.finding_ids
    assert updated_review.no_findings is False


def test_challenge_requires_context_and_intent(tmp_path: Path) -> None:
    service, component_id = _seed(tmp_path)

    challenge = service.submit_challenge(
        project_id="Ageix_Test",
        architecture_id_or_path=component_id,
        submitted_by="lex",
        provider="openai",
        challenge_summary="Architecture review should be represented as collaboration, not health.",
        context="18.2 measures deterministic health only.",
        intent="Keep review discourse separate from health measurement.",
        proposed_direction="Create architecture review/challenge records.",
    )

    assert challenge.challenge_id.startswith("ARCHCHAL-")
    assert challenge.context
    assert challenge.intent


def test_revision_proposal_reuses_existing_proposal_system_and_does_not_mutate_registry(tmp_path: Path) -> None:
    service, component_id = _seed(tmp_path)
    before = service.require_node(component_id).model_dump(mode="json")

    revision = service.propose_revision(
        project_id="Ageix_Test",
        architecture_id_or_path=component_id,
        submitted_by="lex",
        provider="openai",
        objective="Revise architecture review documentation without direct registry mutation.",
        proposed_changes={"description": "Updated description proposal only."},
        metadata={"session_id": "session-18-3"},
    )

    after = service.require_node(component_id).model_dump(mode="json")
    proposal = ProposalService(tmp_path).get_proposal(revision.linked_proposal_id or "")

    assert revision.linked_proposal_id.startswith("PROP-")
    assert revision.metadata["proposal_system_reused"] is True
    assert revision.metadata["direct_registry_mutation"] is False
    assert proposal.proposal_type == "architecture"
    assert proposal.metadata["source"] == "architecture_revision_proposal"
    assert proposal.metadata["requires_chair_approval"] is True
    assert before["description"] == after["description"]


def test_revision_scope_rejects_code_or_implementation_changes(tmp_path: Path) -> None:
    service, component_id = _seed(tmp_path)

    try:
        service.propose_revision(
            project_id="Ageix_Test",
            architecture_id_or_path=component_id,
            submitted_by="lex",
            provider="openai",
            objective="Bad scope.",
            proposed_changes={"code": "modify implementation"},
        )
    except ValueError as exc:
        assert str(exc).startswith("architecture_revision_scope_violation")
    else:
        raise AssertionError("code changes should not be allowed in architecture revision proposals")


def test_18_3_capabilities_are_visible_and_executable_through_mcp(tmp_path: Path) -> None:
    _, component_id = _seed(tmp_path)
    registry = CapabilityRegistryService(tmp_path)
    for capability_id in {
        "architecture.review.submit",
        "architecture.review.get",
        "architecture.review.list",
        "architecture.finding.submit",
        "architecture.challenge.submit",
        "architecture.challenge.get",
        "architecture.challenge.list",
        "architecture.revision.propose",
    }:
        assert registry.exists(capability_id)

    facade = MCPFacadeService(tmp_path)
    tool_names = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}
    for tool_name in {
        "ageix.architecture.review.submit",
        "ageix.architecture.review.get",
        "ageix.architecture.review.list",
        "ageix.architecture.finding.submit",
        "ageix.architecture.challenge.submit",
        "ageix.architecture.challenge.get",
        "ageix.architecture.challenge.list",
        "ageix.architecture.revision.propose",
    }:
        assert tool_name in tool_names

    ctx = _context()
    review = facade.execute_tool("ageix.architecture.review.submit", ctx, {"architecture_id": component_id, "summary": "MCP review.", "no_findings": True})
    assert review.success is True

    listed = facade.execute_tool("ageix.capabilities.list", ctx, {})
    listed_names = {tool["tool_name"] for tool in listed.result["tools"]}
    assert "ageix.architecture.review.submit" in listed_names
    assert "ageix.architecture.revision.propose" in listed_names

    revision = facade.execute_tool("ageix.architecture.revision.propose", ctx, {
        "architecture_id": component_id,
        "objective": "Propose documentation cleanup through proposal governance.",
        "proposed_changes": {"metadata": {"review_notes": "needs cleanup"}},
    })
    assert revision.success is True
    assert revision.result["linked_proposal_id"].startswith("PROP-")
