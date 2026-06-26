from __future__ import annotations

import json
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _all_items(package):
    return package.primary_evidence + package.supporting_evidence + package.validation_evidence


def test_evidence_items_include_provenance_content_hash_and_snapshot(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)

    package = EvidenceBrokerService(tmp_path).request_evidence(proposal_id=decision.proposal_id)

    assert package.repository_snapshot["generated_at"]
    assert "git_commit" in package.repository_snapshot
    item = _all_items(package)[0]
    assert item.content_hash
    assert item.provenance.retrieval_source == "evidence_broker"
    assert item.provenance.retrieval_method in {"intent_plan_hint", "intent_keyword_discovery"}
    assert item.provenance.selection_reason
    assert item.provenance.classification_reason
    assert item.metadata["selection_reason"] == item.provenance.selection_reason


def test_package_rehydration_returns_original_contents_and_reports_freshness(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(proposal_id=decision.proposal_id)
    original_payload = json.loads((tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json").read_text(encoding="utf-8"))
    changed_path = _all_items(package)[0].path
    original_content = _all_items(package)[0].content

    with open(tmp_path / changed_path, "a", encoding="utf-8") as handle:
        handle.write("\n# substantive content drift\n")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17-2",
        agent_id="lex",
        arguments={"project_id": "Ageix", "package_id": package.package_id},
    ))

    assert response.success is True
    assert response.metadata["request_mode"] == "package_rehydration"
    assert response.result["package_id"] == package.package_id
    assert response.result["freshness"]["stale"] is True
    assert changed_path in response.result["freshness"]["changed_paths"]
    rehydrated_items = response.result["primary_evidence"] + response.result["supporting_evidence"] + response.result["validation_evidence"]
    assert any(item["path"] == changed_path and item["content"] == original_content for item in rehydrated_items)

    persisted_after = json.loads((tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json").read_text(encoding="utf-8"))
    assert persisted_after == original_payload


def test_freshness_reports_missing_paths_without_rewriting_package(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(proposal_id=decision.proposal_id)
    missing_path = _all_items(package)[0].path
    (tmp_path / missing_path).unlink()

    rehydrated = EvidenceBrokerService(tmp_path).request_evidence(package_id=package.package_id)

    assert rehydrated.freshness is not None
    assert rehydrated.freshness.stale is True
    assert missing_path in rehydrated.freshness.missing_paths


def test_package_index_created_and_updated_by_freshness(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(proposal_id=decision.proposal_id)

    entries = EvidencePackageIndexService(tmp_path).list_entries()
    entry = [item for item in entries if item["package_id"] == package.package_id][0]
    assert entry["proposal_id"] == decision.proposal_id
    assert entry["primary_count"] == len(package.primary_evidence)
    assert entry["supporting_count"] == len(package.supporting_evidence)
    assert entry["validation_count"] == len(package.validation_evidence)
    assert entry["stale"] is False

    changed_path = _all_items(package)[0].path
    with open(tmp_path / changed_path, "a", encoding="utf-8") as handle:
        handle.write("\n# index freshness drift\n")
    EvidenceBrokerService(tmp_path).request_evidence(package_id=package.package_id)

    updated_entries = EvidencePackageIndexService(tmp_path).list_entries()
    updated = [item for item in updated_entries if item["package_id"] == package.package_id][0]
    assert updated["stale"] is True
    assert updated["freshness_status"] == "modified"
    assert updated["last_freshness_check_at"]


def test_retrieval_guard_denies_sensitive_paths_and_audits(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    (tmp_path / ".env").write_text("SECRET=do-not-return\n", encoding="utf-8")
    payload_path = tmp_path / ".ageix" / "manifests" / "evidence_access_proposals" / decision.proposal_id / "proposal.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["decision"]["evidence_plan"]["resolved_targets"].append({
        "target": ".env",
        "target_type": "file",
        "confidence": 0.99,
        "reason": "malicious or unsafe hint should be denied",
        "metadata": {},
    })
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-2", "agent_id": "lex", "project_id": "Ageix"},
    )

    assert ".env" not in [item.path for item in _all_items(package)]
    records = CapabilityAuditService(tmp_path).list_records()
    denied = [record for record in records if record["reason"] == "evidence_retrieval_denied"]
    assert denied
    assert any(record["metadata"].get("path") == ".env" for record in denied)
