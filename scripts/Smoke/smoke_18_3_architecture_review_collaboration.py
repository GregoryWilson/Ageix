from __future__ import annotations

from pathlib import Path
from pprint import pprint

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = ArchitectureRegistryService(repo_root)
    registry.seed_official_ageix_architecture()

    context = AgeixRequestContext(
        session_id="smoke-18-3-session",
        agent_id="lex",
        project_id="Ageix",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(repo_root)
    tools = facade.discover_tools(category="architecture")
    tool_names = {tool["tool_name"] for tool in tools}

    target_path = "Ageix.Architecture.ArchitectureReviewCollaboration"
    try:
        registry.require_node(target_path)
    except Exception:
        parent = registry.require_node("Ageix.Architecture")
        registry.create_node(
            project_id="Ageix",
            architecture_id="ARCH-AGEIX-ARCHITECTURE-REVIEWCOLLABORATION",
            name="Architecture Review Collaboration",
            node_key="ArchitectureReviewCollaboration",
            parent_id=parent.architecture_id,
            node_type="component",
            description="Governed architecture reviews, findings, challenges, and revision proposal intake.",
            metadata={"seeded_by": "smoke_18_3_architecture_review_collaboration"},
        )

    review = facade.execute_tool("ageix.architecture.review.submit", context, {
        "path": target_path,
        "summary": "Smoke review confirms architecture collaboration intake is published.",
        "no_findings": True,
    })
    review_id = review.result.get("review_id") if review.success else None

    finding = facade.execute_tool("ageix.architecture.finding.submit", context, {
        "review_id": review_id,
        "path": target_path,
        "category": "requires_additional_discovery",
        "severity": "informational",
        "summary": "Future discovery should enrich review coverage.",
    })
    finding_id = finding.result.get("finding_id") if finding.success else None

    challenge = facade.execute_tool("ageix.architecture.challenge.submit", context, {
        "path": target_path,
        "finding_id": finding_id,
        "challenge_summary": "Review collaboration must remain separate from direct architecture mutation.",
        "context": "18.3 captures discourse and proposed revisions.",
        "intent": "Preserve Chair-governed architecture changes.",
        "proposed_direction": "Route changes through revision proposals linked to the existing proposal system.",
    })
    challenge_id = challenge.result.get("challenge_id") if challenge.success else None

    revision = facade.execute_tool("ageix.architecture.revision.propose", context, {
        "path": target_path,
        "challenge_id": challenge_id,
        "objective": "Propose documentation refinement for architecture review collaboration.",
        "proposed_changes": {"description": "Clarify that reviews and challenges do not directly mutate the architecture registry."},
    })

    listed = facade.execute_tool("ageix.capabilities.list", context, {})
    listed_names = {tool["tool_name"] for tool in listed.result.get("tools", [])} if listed.success else set()

    expected = {
        "ageix.architecture.review.submit",
        "ageix.architecture.review.get",
        "ageix.architecture.review.list",
        "ageix.architecture.finding.submit",
        "ageix.architecture.challenge.submit",
        "ageix.architecture.challenge.get",
        "ageix.architecture.challenge.list",
        "ageix.architecture.revision.propose",
    }
    report = {
        "architecture_tool_count": len(tools),
        "all_expected_tools_discovered": expected.issubset(tool_names),
        "all_expected_tools_listed": expected.issubset(listed_names),
        "review_success": review.success,
        "finding_success": finding.success,
        "challenge_success": challenge.success,
        "revision_success": revision.success,
        "review_id": review_id,
        "finding_id": finding_id,
        "challenge_id": challenge_id,
        "linked_proposal_id": revision.result.get("linked_proposal_id") if revision.success else None,
        "direct_registry_mutation": revision.result.get("metadata", {}).get("direct_registry_mutation") if revision.success else None,
        "proposal_system_reused": revision.result.get("metadata", {}).get("proposal_system_reused") if revision.success else None,
    }

    print("== Smoke 18.3: Architecture review collaboration foundation ==")
    pprint(report)

    assert report["all_expected_tools_discovered"] is True
    assert report["all_expected_tools_listed"] is True
    assert report["review_success"] is True
    assert report["finding_success"] is True
    assert report["challenge_success"] is True
    assert report["revision_success"] is True
    assert str(report["linked_proposal_id"] or "").startswith("PROP-")
    assert report["direct_registry_mutation"] is False
    assert report["proposal_system_reused"] is True

    print("Smoke 18.3 PASS: governed architecture reviews, findings, challenges, revision proposal handoff, and MCP publication validated.")


if __name__ == "__main__":
    main()
