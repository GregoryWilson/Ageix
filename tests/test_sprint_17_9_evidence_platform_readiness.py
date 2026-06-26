from __future__ import annotations

import json
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.evidence_platform_readiness_service import EvidencePlatformReadinessService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _package(tmp_path: Path, *, smoke_demo: bool = False):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-9", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
    )
    if smoke_demo:
        package.lifecycle = {"artifact_type": "smoke_demo", "cleanup_eligible": True, "created_for_sprint": "17.9"}
        package_path = tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json"
        package_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
        EvidencePackageIndexService(tmp_path).upsert_package(package)
    return decision, package


def test_readiness_assessment_reports_pass_without_repair_or_cleanup(tmp_path: Path):
    _, package = _package(tmp_path, smoke_demo=True)

    result = EvidencePlatformReadinessService(tmp_path).assess()

    assert result["readiness_status"] == "pass"
    assert result["ready_for_architecture_hierarchy"] is True
    assert result["validation_only"] is True
    assert result["repair_performed"] is False
    assert result["cleanup_performed"] is False
    assert result["package_health"]["package_count"] == 1
    assert result["package_health"]["fresh_package_count"] == 1
    assert result["package_health"]["smoke_demo_cleanup_candidate_count"] == 1
    assert result["package_health"]["cleanup_candidate_package_ids"] == [package.package_id]
    assert (tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json").exists()


def test_readiness_artifact_is_written_as_machine_readable_json(tmp_path: Path):
    _package(tmp_path)

    service = EvidencePlatformReadinessService(tmp_path)
    result = service.assess(write_artifact=True)
    artifact = tmp_path / ".ageix" / "readiness" / "evidence_platform_readiness.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert artifact.exists()
    assert payload["schema_version"] == 1
    assert payload["sprint"] == "17.9"
    assert payload["summary"] == result["summary"]
    assert payload["summary"]["mcp_evidence_access"] == "pass"


def test_readiness_detects_index_breakage_without_repairing(tmp_path: Path):
    _, package = _package(tmp_path)
    package_dir = tmp_path / ".ageix" / "evidence_packages" / package.package_id
    for path in package_dir.glob("*"):
        path.unlink()
    package_dir.rmdir()

    result = EvidencePlatformReadinessService(tmp_path).assess()

    assert result["readiness_status"] == "fail"
    assert result["repair_performed"] is False
    assert result["index_validation"]["status"] == "fail"
    assert package.package_id in result["index_validation"]["missing_package_dirs"]
    assert not package_dir.exists()


def test_readiness_validates_mcp_evidence_and_decision_trace_governance(tmp_path: Path):
    _package(tmp_path)

    result = EvidencePlatformReadinessService(tmp_path).assess()
    mcp = result["mcp_exposure_health"]

    assert mcp["status"] == "pass"
    assert mcp["evidence_access_status"] == "pass"
    assert mcp["decision_trace_governance_status"] == "pass"
    assert mcp["missing_required_tools"] == []
    assert mcp["forbidden_tools_visible"] == []
    assert mcp["forbidden_capabilities_visible"] == []
    assert mcp["decision_trace_create_registry_exposed"] is False


def test_readiness_includes_decision_trace_count_without_requiring_traces(tmp_path: Path):
    decision, package = _package(tmp_path)
    created = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="decision.trace.create",
        session_id="chair-17-9",
        agent_id="chair",
        arguments={
            "project_id": "Ageix",
            "decision_summary": "Close Sprint 17 evidence platform",
            "outcome": "approved",
            "proposal_id": decision.proposal_id,
            "evidence_package_ids": [package.package_id],
        },
    ))

    result = EvidencePlatformReadinessService(tmp_path).assess()

    assert created.success is True
    assert result["decision_trace_health"]["status"] == "pass"
    assert result["decision_trace_health"]["trace_count"] == 1
    assert result["summary"]["decision_trace_count"] == 1
