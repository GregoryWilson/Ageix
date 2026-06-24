from __future__ import annotations

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
from services.architecture_work_context_service import ArchitectureWorkContextService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def _context() -> AgeixRequestContext:
    return AgeixRequestContext(session_id="smoke-18-9", agent_id="lex", project_id="Ageix_Test", client_id="chatGPT", provider="chatGPT", authentication_method="dev_token")


def _approve(repo: Path, proposal_id: str) -> str:
    ProposalService(repo).update_status(proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(repo).create_trace(
        decision_summary="Smoke approved work context artifact.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "smoke-18-9"},
        proposal_id=proposal_id,
        evidence_package_ids=[],
        reason="Smoke validation requires governed accepted guidance.",
    )
    return trace.trace_id


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ageix-smoke-18-9-") as tmp:
        repo = Path(tmp)
        registry = ArchitectureRegistryService(repo)
        project = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-PROJECT", name="Smoke Project", node_key="SmokeProject", path="SmokeProject", node_type="project", description="Smoke project root.")
        downstream = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-DOWNSTREAM", name="Smoke Downstream", node_key="SmokeDownstream", parent_id=project.architecture_id, node_type="domain", description="Smoke downstream node.")
        component = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-WORKCTX", name="Smoke Work Context", node_key="SmokeWorkContext", parent_id=project.architecture_id, node_type="domain", description="Smoke work context node.", metadata={"relationships": {"downstream": [downstream.architecture_id]}})

        guidance = ArchitectureGuidanceService(repo)
        principle = guidance.propose_principle(project_id="Ageix_Test", session_id="smoke-18-9", created_by="lex", title="Smoke work governance", statement="Smoke work context remains governed.", architecture_ids=[project.architecture_id])
        trace_id = _approve(repo, principle.proposal_id)
        guidance.accept_approved_principle(principle.principle_id, approved_by="chair", decision_trace_id=trace_id)

        facade = MCPFacadeService(repo)
        generated = facade.execute_tool("ageix.architecture.work.context", _context(), {"architecture_id": component.architecture_id, "work_summary": "Smoke work context retrieval."})
        persisted = facade.execute_tool("ageix.architecture.work.context", _context(), {"architecture_id": component.architecture_id, "persist": True, "persist_guidance_context": True})
        filtered = facade.execute_tool("ageix.capabilities.list", _context(), {"category": "architecture", "query": "work.context", "limit": 10, "offset": 0})

        if not generated.success or generated.result.get("persisted_snapshot") is not False:
            raise AssertionError("generated work context failed")
        if not persisted.success or not str(persisted.result.get("work_context_id", "")).startswith("WORKCTX-"):
            raise AssertionError("persisted work context failed")
        if not persisted.result.get("guidance_context_package_ids"):
            raise AssertionError("persisted work context did not persist guidance context")
        if not filtered.success or filtered.result.get("count", 0) < 2:
            raise AssertionError("filtered work context capabilities failed")
        if not persisted.result.get("impacted_nodes"):
            raise AssertionError("impact analysis did not surface direct relationship")

        work_context_id = persisted.result["work_context_id"]
        guidance_context_ids = list(persisted.result.get("guidance_context_package_ids") or [])
        ArchitectureWorkContextService(repo).cleanup_package(work_context_id)
        for package_id in guidance_context_ids:
            ArchitectureGuidanceContextService(repo).cleanup_package(package_id)
        if (repo / ".ageix" / "architecture" / "work_context" / work_context_id).exists():
            raise AssertionError("smoke work context cleanup failed")
        for package_id in guidance_context_ids:
            if (repo / ".ageix" / "architecture" / "guidance_context" / package_id).exists():
                raise AssertionError("smoke guidance context cleanup failed")

        print("== Smoke 18.9: Architecture work analysis foundation ==")
        print({
            "generated_work_context_id": generated.result.get("work_context_id"),
            "persisted_work_context_id": work_context_id,
            "persisted_guidance_context_ids": guidance_context_ids,
            "impacted_node_count": len(persisted.result.get("impacted_nodes", [])),
            "capability_count": filtered.result.get("count"),
            "cleanup_verified": True,
        })
        print("Smoke 18.9 PASS: work context packaging, deterministic scope resolution, direct impact analysis, MCP retrieval, and cleanup validated.")


if __name__ == "__main__":
    main()
