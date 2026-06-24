from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context() -> AgeixRequestContext:
    return AgeixRequestContext(session_id="smoke-18-8", agent_id="lex", project_id="Ageix_Test", client_id="chatGPT", provider="chatGPT", authentication_method="dev_token")


def _approve(repo: Path, proposal_id: str) -> str:
    ProposalService(repo).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(repo).create_trace(
        decision_summary="Smoke approved guidance context artifact.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "smoke-18-8"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Smoke validation requires governed accepted guidance.",
    )
    return trace.trace_id


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ageix-smoke-18-8-") as tmp:
        repo = Path(tmp)
        registry = ArchitectureRegistryService(repo)
        project = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-PROJECT", name="Smoke Project", node_key="SmokeProject", path="SmokeProject", node_type="project", description="Smoke project root.")
        component = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-COMPONENT", name="Smoke Guidance Context", node_key="SmokeGuidanceContext", parent_id=project.architecture_id, node_type="domain", description="Smoke guidance context node.")

        guidance = ArchitectureGuidanceService(repo)
        principle = guidance.propose_principle(project_id="Ageix_Test", session_id="smoke-18-8", created_by="lex", title="Smoke governance", statement="Smoke guidance context remains governed.", architecture_ids=[project.architecture_id])
        trace_id = _approve(repo, principle.proposal_id)
        principle = guidance.accept_approved_principle(principle.principle_id, approved_by="chair", decision_trace_id=trace_id)

        facade = MCPFacadeService(repo)
        generated = facade.execute_tool("ageix.architecture.guidance.context", _context(), {"architecture_id": component.architecture_id})
        persisted = facade.execute_tool("ageix.architecture.guidance.context", _context(), {"architecture_id": component.architecture_id, "persist": True})
        filtered = facade.execute_tool("ageix.capabilities.list", _context(), {"category": "architecture", "query": "guidance", "limit": 10, "offset": 0})

        if not generated.success or generated.result.get("persisted_snapshot") is not False:
            raise AssertionError("generated guidance context failed")
        if not persisted.success or not str(persisted.result.get("package_id", "")).startswith("GUIDECTX-"):
            raise AssertionError("persisted guidance context failed")
        if not filtered.success or filtered.result.get("count", 0) < 1:
            raise AssertionError("filtered capabilities list failed")

        package_id = persisted.result["package_id"]
        ArchitectureGuidanceContextService(repo).cleanup_package(package_id)
        if (repo / ".ageix" / "architecture" / "guidance_context" / package_id).exists():
            raise AssertionError("smoke guidance context cleanup failed")

        print("== Smoke 18.8: Architecture guidance context maturity ==")
        print({
            "generated_package_id": generated.result.get("package_id"),
            "persisted_package_id": package_id,
            "principle_count": len(generated.result.get("governing_principles", [])),
            "capability_count": filtered.result.get("count"),
            "cleanup_verified": True,
        })
        print("Smoke 18.8 PASS: guidance context packaging, MCP retrieval, capability filtering, and cleanup validated.")


if __name__ == "__main__":
    main()
