from __future__ import annotations

import argparse
import pprint
import tempfile
from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext


def run(repo_root: Path, quiet: bool = False) -> dict:
    service = ArchitectureRegistryService(repo_root)
    seed = service.seed_official_ageix_architecture()
    service.ensure_reviewers()

    context = AgeixRequestContext(
        session_id="smoke-18-0-session",
        agent_id="lex",
        project_id="Ageix",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(repo_root)
    tools = facade.discover_tools(category="architecture")
    domains = facade.execute_tool("ageix.architecture.list", context, {"node_type": "domain"})
    evidence_children = facade.execute_tool("ageix.architecture.children", context, {"path": "Ageix.Evidence"})
    mcp_access = facade.execute_tool("ageix.architecture.details", context, {"path": "Ageix.Evidence.MCPEvidenceAccess"})
    subtree = facade.execute_tool("ageix.architecture.subtree", context, {"path": "Ageix.MCPPlatform"})

    result = {
        "seeded": seed.get("seeded"),
        "architecture_tool_count": len(tools),
        "domain_count": domains.result.get("count"),
        "evidence_child_count": evidence_children.result.get("count"),
        "mcp_evidence_access_path": mcp_access.result.get("path"),
        "mcp_platform_subtree_root": subtree.result.get("subtree", {}).get("node", {}).get("path"),
        "chair_authority_preserved": all(item.governance.get("chair_authority_preserved") for item in [domains, evidence_children, mcp_access, subtree]),
    }
    if not quiet:
        print("== Smoke 18.0: Architecture hierarchy foundation ==")
        pprint.pp(result)
    assert result["architecture_tool_count"] >= 4
    assert result["domain_count"] >= 6
    assert result["evidence_child_count"] >= 5
    assert result["mcp_evidence_access_path"] == "Ageix.Evidence.MCPEvidenceAccess"
    assert result["mcp_platform_subtree_root"] == "Ageix.MCPPlatform"
    assert result["chair_authority_preserved"] is True
    if not quiet:
        print("Smoke 18.0 PASS: architecture registry, hierarchy, MCP discovery/retrieval, and official Ageix seed validated.")
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
