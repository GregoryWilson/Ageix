from __future__ import annotations

import shutil
from pathlib import Path
from pprint import pprint

from models.proposal import ProposalStatus
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.architecture_registry_service import ArchitectureRegistryService
from services.decision_trace_service import DecisionTraceService
from services.proposal_service import ProposalService

PROJECT_ID = "Ageix_Test"
ARCH_ID = "ARCH-SMOKE-18-6-ADR"


def cleanup(repo_root: Path) -> None:
    for root in [
        repo_root / ".ageix" / "architecture" / "adrs",
        repo_root / ".ageix" / "manifests" / "proposals",
        repo_root / ".ageix" / "decision_traces",
    ]:
        if root.exists():
            for path in root.iterdir():
                if path.is_dir() and ("SMOKE" in path.name or path.name.startswith("ADR-") or path.name.startswith("PROP-") or path.name.startswith("TRACE-")):
                    shutil.rmtree(path, ignore_errors=True)
    node_path = repo_root / ".ageix" / "architecture" / "nodes" / f"{ARCH_ID}.json"
    if node_path.exists():
        node_path.unlink()


def main() -> None:
    repo_root = Path.cwd()
    print("== Smoke 18.6: Architecture Decision Records ==")
    cleanup(repo_root)

    registry = ArchitectureRegistryService(repo_root)
    try:
        registry.create_node(project_id=PROJECT_ID, architecture_id=ARCH_ID, name="Smoke ADR", node_key="SmokeADR", path="SmokeADR", node_type="component", description="Smoke ADR component.")
    except Exception:
        pass

    service = ArchitectureDecisionRecordService(repo_root)
    adr = service.propose_adr(
        project_id=PROJECT_ID,
        session_id="smoke-18-6",
        created_by="lex",
        title="Smoke ADR governance",
        context="Smoke validates ADR proposal and acceptance flow.",
        decision="ADRs are proposed through governance and accepted only after proposal approval.",
        rationale="This preserves architectural reasoning without direct MCP acceptance.",
        architecture_ids=[ARCH_ID],
        evidence_package_ids=["EVPKG-SMOKE-NAPKIN"],
        metadata={"smoke": True},
    )
    ProposalService(repo_root).update_status(adr.proposal_id, ProposalStatus.APPROVED)
    trace = DecisionTraceService(repo_root).create_trace(
        decision_summary="Smoke approved ADR.",
        outcome="approved",
        requester_identity={"agent_id": "chair", "project_id": PROJECT_ID, "session_id": "smoke-18-6"},
        proposal_id=adr.proposal_id,
        evidence_package_ids=[],
        reason="Smoke evidence sufficient.",
    )
    accepted = service.accept_approved_adr(adr.adr_id, approved_by="chair", decision_trace_id=trace.trace_id)
    listed = service.list_adrs(project_id=PROJECT_ID)
    history = service.get_history(accepted.adr_id)

    result = {
        "adr_id": accepted.adr_id,
        "adr_number": accepted.adr_number,
        "status": accepted.status.value,
        "proposal_id": accepted.proposal_id,
        "decision_trace_id": accepted.decision_trace_id,
        "listed_count": listed["count"],
        "history_count": history["count"],
    }
    pprint(result)

    assert accepted.status.value == "accepted"
    assert accepted.decision_trace_id == trace.trace_id
    assert listed["count"] >= 1
    assert history["count"] == 1

    cleanup(repo_root)
    print("Smoke 18.6 PASS: ADR proposal, governed acceptance, lineage, history, and cleanup validated.")


if __name__ == "__main__":
    main()
