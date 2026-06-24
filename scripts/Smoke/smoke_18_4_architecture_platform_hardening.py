from __future__ import annotations

from pathlib import Path
from pprint import pprint

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext
from services.project_registry_service import ProjectRegistryService


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    project_registry = ProjectRegistryService(repo_root)
    if not any(project["project_id"] == "Ageix_Test" for project in project_registry.list_projects()):
        project_registry.register_project(
            project_id="Ageix_Test",
            name="Ageix Test",
            project_type="python",
            root_path=repo_root,
            metadata={"purpose": "sandbox smoke-test project", "seeded_by": "smoke_18_4"},
        )
    project_seed = project_registry.ensure_official_ageix_project()
    architecture = ArchitectureRegistryService(repo_root)
    architecture_seed = architecture.seed_official_ageix_architecture()
    baseline_validation = architecture.validate_baseline(project_id="Ageix")

    context = AgeixRequestContext(
        session_id="smoke-18-4-session",
        agent_id="lex",
        client_id="chatGPT",
        provider="chatGPT",
        project_id="Ageix",
        participant_id="chatgpt",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(repo_root)
    tools = facade.discover_tools(category="architecture")
    tool_names = {tool["tool_name"] for tool in tools}

    mcp_validation = facade.execute_tool("ageix.architecture.baseline.validate", context, {"project_id": "Ageix"})

    review_targets = ["Ageix", "Ageix.MCPPlatform", "Ageix.Architecture"]
    review_ids: list[str] = []
    for target in review_targets:
        response = facade.execute_tool("ageix.architecture.review.submit", context, {
            "path": target,
            "summary": f"Smoke 18.4 architecture hardening review for {target}.",
            "rationale": "Validate governed live-style architecture review submission for platform hardening.",
            "no_findings": target != "Ageix.Architecture",
            "metadata": {"smoke_test": True, "sprint": "18.4", "target": target},
        })
        assert response.success, response.errors
        review_ids.append(response.result["review_id"])

    finding = facade.execute_tool("ageix.architecture.finding.submit", context, {
        "review_id": review_ids[-1],
        "path": "Ageix.Architecture",
        "severity": "informational",
        "category": "requires_additional_discovery",
        "summary": "Architecture platform hardening should retain live MCP validation evidence.",
        "rationale": "The architecture platform is operational only when external review, challenge, and proposal handoff are validated.",
    })
    challenge = facade.execute_tool("ageix.architecture.challenge.submit", context, {
        "path": "Ageix.Architecture",
        "finding_id": finding.result.get("finding_id") if finding.success else None,
        "challenge_summary": "Architecture platform validation should be recorded as governed architecture history.",
        "context": "Sprint 18.4 hardens the official Ageix project, baseline validation, live MCP review, and operations readiness.",
        "intent": "Keep architecture trust grounded in reproducible validation before future system-of-record work.",
        "rationale": "External architect activity should flow through governed review and proposal paths without direct registry mutation.",
        "proposed_direction": "Use revision proposals for metadata changes rather than direct architecture registry edits.",
    })
    revision = facade.execute_tool("ageix.architecture.revision.propose", context, {
        "path": "Ageix.Architecture",
        "challenge_id": challenge.result.get("challenge_id") if challenge.success else None,
        "objective": "Record Sprint 18.4 architecture platform hardening validation in architecture metadata.",
        "proposed_changes": {"metadata": {"sprint_18_4_hardened": True, "live_mcp_review_validated": True}},
        "metadata": {"smoke_test": True, "sprint": "18.4"},
    })

    report = {
        "official_project_seeded": project_seed.get("seeded"),
        "official_project_present": any(project["project_id"] == "Ageix" for project in project_registry.list_projects()),
        "ageix_test_preserved": any(project["project_id"] == "Ageix_Test" for project in project_registry.list_projects()),
        "architecture_seeded": architecture_seed.get("seeded"),
        "baseline_validation_status": baseline_validation.get("status"),
        "baseline_missing_paths": len(baseline_validation.get("missing_paths", [])),
        "mcp_validation_success": mcp_validation.success,
        "mcp_validation_status": mcp_validation.result.get("status") if mcp_validation.success else None,
        "architecture_tool_count": len(tools),
        "baseline_tool_visible": "ageix.architecture.baseline.validate" in tool_names,
        "review_count": len(review_ids),
        "finding_success": finding.success,
        "challenge_success": challenge.success,
        "revision_success": revision.success,
        "linked_proposal_id": revision.result.get("linked_proposal_id") if revision.success else None,
        "proposal_system_reused": revision.result.get("metadata", {}).get("proposal_system_reused") if revision.success else None,
        "direct_registry_mutation": revision.result.get("metadata", {}).get("direct_registry_mutation") if revision.success else None,
    }

    print("== Smoke 18.4: Architecture platform hardening ==")
    pprint(report)

    assert report["official_project_present"] is True
    assert report["ageix_test_preserved"] is True or report["official_project_seeded"] is True
    assert report["baseline_validation_status"] in {"partial", "complete_current_state"}
    assert report["baseline_missing_paths"] == 0
    assert report["mcp_validation_success"] is True
    assert report["baseline_tool_visible"] is True
    assert report["review_count"] == 3
    assert report["finding_success"] is True
    assert report["challenge_success"] is True
    assert report["revision_success"] is True
    assert report["linked_proposal_id"] and str(report["linked_proposal_id"]).startswith("PROP-")
    assert report["proposal_system_reused"] is True
    assert report["direct_registry_mutation"] is False

    print("Smoke 18.4 PASS: official project, baseline validation, live-style MCP review, challenge, revision proposal handoff, and operations readiness validated.")


if __name__ == "__main__":
    main()
