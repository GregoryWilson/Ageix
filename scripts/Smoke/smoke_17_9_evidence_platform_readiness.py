from __future__ import annotations

import tempfile
from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.evidence_platform_readiness_service import EvidencePlatformReadinessService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def main() -> int:
    print("== Smoke 17.9: evidence platform readiness and closure ==")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        decision = _approved_intent_plan(repo)
        package = EvidenceBrokerService(repo).request_evidence(
            proposal_id=decision.proposal_id,
            requester_identity={"session_id": "smoke-17-9", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
        )
        package.lifecycle = {"artifact_type": "smoke_demo", "cleanup_eligible": True, "created_for_sprint": "17.9"}
        package_path = repo / ".ageix" / "evidence_packages" / package.package_id / "package.json"
        package_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
        EvidencePackageIndexService(repo).upsert_package(package)

        trace = CapabilityExecutionService(repo).execute(CapabilityRequest(
            capability_id="decision.trace.create",
            session_id="chair-smoke-17-9",
            agent_id="chair",
            arguments={
                "project_id": "Ageix",
                "decision_summary": "Sprint 17 evidence platform closure readiness",
                "outcome": "approved",
                "proposal_id": decision.proposal_id,
                "evidence_package_ids": [package.package_id],
                "reason": "Chair validates evidence platform closure before architecture hierarchy.",
            },
        ))
        assert trace.success, trace.error

        readiness = EvidencePlatformReadinessService(repo).assess(write_artifact=True)
        artifact = repo / ".ageix" / "readiness" / "evidence_platform_readiness.json"

        assert readiness["readiness_status"] == "pass", readiness["issues"]
        assert readiness["ready_for_architecture_hierarchy"] is True
        assert readiness["validation_only"] is True
        assert readiness["repair_performed"] is False
        assert readiness["cleanup_performed"] is False
        assert readiness["index_validation"]["status"] == "pass"
        assert readiness["package_health"]["package_count"] == 1
        assert readiness["package_health"]["smoke_demo_cleanup_candidate_count"] == 1
        assert readiness["decision_trace_health"]["trace_count"] == 1
        assert readiness["mcp_exposure_health"]["evidence_access_status"] == "pass"
        assert readiness["mcp_exposure_health"]["decision_trace_governance_status"] == "pass"
        assert readiness["mcp_exposure_health"]["decision_trace_create_registry_exposed"] is False
        assert artifact.exists()
        assert package_path.exists()

        pprint({
            "artifact": str(artifact.relative_to(repo)),
            "package_id": package.package_id,
            "trace_id": trace.result["trace_id"],
            "readiness_status": readiness["readiness_status"],
            "package_count": readiness["summary"]["package_count"],
            "fresh_package_count": readiness["summary"]["fresh_package_count"],
            "cleanup_candidates": readiness["summary"]["smoke_demo_cleanup_candidate_count"],
            "mcp_evidence_access": readiness["summary"]["mcp_evidence_access"],
            "decision_trace_governance": readiness["summary"]["decision_trace_governance"],
        })
    print("Smoke 17.9 PASS: evidence platform readiness artifact, validation-only health summary, MCP exposure, decision trace governance, and no cleanup/repair behavior validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
