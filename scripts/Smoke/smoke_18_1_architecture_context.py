from __future__ import annotations

import argparse
import json
import pprint
import tempfile
from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_context_service import ArchitectureContextService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext


def _seed_supporting_indexes(repo_root: Path) -> None:
    evidence_root = repo_root / ".ageix" / "evidence_packages"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "index.json").write_text(json.dumps({"packages": [{
        "package_id": "EVPKG-18-1",
        "project_id": "Ageix",
        "objective": "Architecture context smoke evidence summary",
        "proposal_id": "EAP-18-1",
        "evidence_plan_id": "EVP-18-1",
        "freshness_status": "unchanged",
        "stale": False,
        "primary_count": 1,
        "supporting_count": 2,
        "validation_count": 1,
        "governance": {"status": "active"},
    }]}, indent=2), encoding="utf-8")
    decision_root = repo_root / ".ageix" / "decision_traces"
    decision_root.mkdir(parents=True, exist_ok=True)
    (decision_root / "index.json").write_text(json.dumps({"traces": [{
        "trace_id": "TRACE-18-1",
        "project_id": "Ageix",
        "decision_id": "DEC-18-1",
        "decision_type": "architecture",
        "decision_summary": "Approve architecture context as summary-first and evidence-linked.",
        "outcome": "approved",
        "proposal_id": "PROP-18-1",
        "evidence_package_ids": ["EVPKG-18-1"],
        "created_at": "2026-06-23T00:00:00+00:00",
    }]}, indent=2), encoding="utf-8")


def run(repo_root: Path, quiet: bool = False) -> dict:
    registry = ArchitectureRegistryService(repo_root)
    registry.seed_official_ageix_architecture()
    _seed_supporting_indexes(repo_root)
    node = registry.link_evidence("Ageix.Architecture.ArchitectureRegistry", ["EVPKG-18-1"], ["TRACE-18-1"])
    context_service = ArchitectureContextService(repo_root)
    description = context_service.create_description(
        node.architecture_id,
        purpose="Represent the durable architecture hierarchy for Ageix.",
        responsibilities=["Maintain project/domain/component hierarchy", "Support architecture-aware context generation"],
        boundaries=["Does not own evidence package contents", "Does not perform architecture scoring"],
        open_questions=["Review board workflow deferred to a later sprint"],
        detailed_description="Architecture context can retain detail while default worker packets remain summary-first.",
    )
    context_service.approve_description(description.description_id, approved_by="chair")

    request_context = AgeixRequestContext(
        session_id="smoke-18-1-session",
        agent_id="lex",
        project_id="Ageix",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(repo_root)
    tools = facade.discover_tools(category="architecture")
    context_response = facade.execute_tool("ageix.architecture.context", request_context, {"path": "Ageix.Architecture.ArchitectureRegistry"})
    detail_response = facade.execute_tool("ageix.architecture.context", request_context, {"path": "Ageix.Architecture.ArchitectureRegistry", "include_detail": True})

    result = {
        "architecture_context_tool_visible": "ageix.architecture.context" in {tool["tool_name"] for tool in tools},
        "architecture_tool_count": len(tools),
        "context_success": context_response.success,
        "summary_first": context_response.result.get("context_policy", {}).get("summary_first"),
        "repo_discovery": context_response.result.get("context_policy", {}).get("repository_wide_discovery_performed"),
        "evidence_summary_count": len(context_response.result.get("linked_evidence_summary", [])),
        "decision_summary_count": len(context_response.result.get("linked_decision_summary", [])),
        "detail_in_default_response": bool(context_response.result.get("detail")),
        "detail_opt_in": bool(detail_response.result.get("detail")),
        "chair_authority_preserved": context_response.governance.get("chair_authority_preserved") is True,
    }
    if not quiet:
        print("== Smoke 18.1: Architecture context foundation ==")
        pprint.pp(result)
    assert result["architecture_context_tool_visible"] is True
    assert result["architecture_tool_count"] >= 5
    assert result["context_success"] is True
    assert result["summary_first"] is True
    assert result["repo_discovery"] is False
    assert result["evidence_summary_count"] == 1
    assert result["decision_summary_count"] == 1
    assert result["detail_in_default_response"] is False
    assert result["detail_opt_in"] is True
    assert result["chair_authority_preserved"] is True
    if not quiet:
        print("Smoke 18.1 PASS: MCP publication, description lifecycle, summary-first architecture context, and evidence/decision linking validated.")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()
    if args.repo_root:
        run(Path(args.repo_root), quiet=args.quiet)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            run(Path(tmp), quiet=args.quiet)
