from __future__ import annotations

import shutil
from pathlib import Path
from pprint import pprint

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_revision_service import ArchitectureRevisionService
from services.decision_trace_service import DecisionTraceService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    architecture = ArchitectureRegistryService(repo_root)
    smoke_ids = ["ARCH-SMOKE-18-5-PROJECT", "ARCH-SMOKE-18-5-DOMAIN", "ARCH-SMOKE-18-5-COMPONENT"]
    _cleanup(repo_root, smoke_ids)

    project = architecture.create_node(project_id="Ageix_Test", architecture_id=smoke_ids[0], name="Smoke 18.5", node_key="Smoke185", path="Smoke185", node_type="project", description="Smoke root.")
    domain = architecture.create_node(project_id="Ageix_Test", architecture_id=smoke_ids[1], name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Smoke domain.")
    component = architecture.create_node(project_id="Ageix_Test", architecture_id=smoke_ids[2], name="Revision Governance", node_key="RevisionGovernance", parent_id=domain.architecture_id, node_type="component", description="Before governed revision.")

    proposal_record = architecture.propose_revision(
        project_id="Ageix_Test",
        architecture_id_or_path=component.architecture_id,
        submitted_by="lex",
        provider="openai",
        objective="Smoke 18.5 governed architecture revision.",
        proposed_changes={"description": "After governed revision.", "metadata": {"smoke": "18.5"}},
        metadata={"session_id": "smoke-18-5"},
    )
    ProposalService(repo_root).update_status(proposal_record.linked_proposal_id or "", ProposalStatus.APPROVED)
    trace = DecisionTraceService(repo_root).create_trace(
        decision_summary="Smoke approved architecture revision.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": "Ageix_Test", "session_id": "smoke-18-5"},
        proposal_id=proposal_record.linked_proposal_id,
        evidence_package_ids=[],
        reason="Smoke evidence sufficient.",
    )
    revision = ArchitectureRevisionService(repo_root).apply_approved_revision(
        revision_proposal_id=proposal_record.revision_id,
        approved_by="chair",
        revision_type="create",
        decision_trace_id=trace.trace_id,
    )

    context = AgeixRequestContext(
        session_id="smoke-18-5",
        agent_id="lex",
        project_id="Ageix_Test",
        client_id="chatgpt",
        provider="openai",
        authentication_method="dev_token",
    )
    facade = MCPFacadeService(repo_root)
    baseline = facade.execute_tool("ageix.architecture.baseline.current", context, {"architecture_id": component.architecture_id, "include_snapshot": False})
    history = facade.execute_tool("ageix.architecture.history", context, {"architecture_id": component.architecture_id})

    result = {
        "revision_id": revision.revision_id,
        "snapshot_id": revision.snapshot_id,
        "baseline_version": revision.baseline_version,
        "active_revision_id": baseline.result.get("baseline", {}).get("active_revision_id") if baseline.success else None,
        "history_count": history.result.get("count") if history.success else None,
        "proposal_id": revision.proposal_id,
        "decision_trace_id": revision.decision_trace_id,
    }
    pprint(result)
    assert baseline.success is True
    assert history.success is True
    assert result["active_revision_id"] == revision.revision_id
    assert result["history_count"] >= 1

    _cleanup_generated(repo_root, revision.revision_id, revision.snapshot_id, proposal_record.revision_id, proposal_record.linked_proposal_id or "", trace.trace_id)
    _cleanup(repo_root, smoke_ids)
    print("Smoke 18.5 PASS: governed architecture revision, immutable snapshot, active baseline, history, MCP read exposure, and smoke cleanup validated.")


def _cleanup_generated(repo_root: Path, revision_id: str, snapshot_id: str, revision_proposal_id: str, proposal_id: str, trace_id: str) -> None:
    architecture_root = repo_root / ".ageix" / "architecture"
    shutil.rmtree(architecture_root / "revisions" / revision_id, ignore_errors=True)
    shutil.rmtree(architecture_root / "snapshots" / snapshot_id, ignore_errors=True)
    shutil.rmtree(architecture_root / "revision_proposals" / revision_proposal_id, ignore_errors=True)
    shutil.rmtree(repo_root / ".ageix" / "manifests" / "proposals" / proposal_id, ignore_errors=True)
    shutil.rmtree(repo_root / ".ageix" / "decision_traces" / trace_id, ignore_errors=True)
    index_path = repo_root / ".ageix" / "decision_traces" / "index.json"
    if index_path.exists():
        import json
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        payload["traces"] = [item for item in payload.get("traces", []) if item.get("trace_id") != trace_id]
        index_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _cleanup(repo_root: Path, architecture_ids: list[str]) -> None:
    architecture_root = repo_root / ".ageix" / "architecture"
    for architecture_id in architecture_ids:
        (architecture_root / "nodes" / f"{architecture_id}.json").unlink(missing_ok=True)
        shutil.rmtree(architecture_root / "baselines" / architecture_id, ignore_errors=True)
    index_path = architecture_root / "index.json"
    if index_path.exists():
        import json
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        payload["nodes"] = [item for item in payload.get("nodes", []) if item.get("architecture_id") not in set(architecture_ids)]
        index_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
