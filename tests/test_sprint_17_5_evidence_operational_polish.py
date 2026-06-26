from __future__ import annotations

from pathlib import Path

from models.evidence_package import PackageLineageType
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_cleanup_service import EvidencePackageCleanupService
from services.evidence_package_index_service import EvidencePackageIndexService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _package(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-5", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
    )
    return package


def test_cleanup_deletes_only_explicit_smoke_demo_packages_and_rebuilds_index(tmp_path: Path):
    real = _package(tmp_path)
    smoke = _package(tmp_path)
    smoke.lifecycle = {"artifact_type": "smoke_demo", "cleanup_eligible": True, "created_for_sprint": "17.5"}
    package_path = tmp_path / ".ageix" / "evidence_packages" / smoke.package_id / "package.json"
    package_path.write_text(smoke.model_dump_json(indent=2), encoding="utf-8")
    EvidencePackageIndexService(tmp_path).upsert_package(smoke)

    dry_run = EvidencePackageCleanupService(tmp_path).cleanup_smoke_demo_packages(dry_run=True)
    assert dry_run["candidate_count"] == 1
    assert dry_run["candidates"][0]["package_id"] == smoke.package_id
    assert (tmp_path / ".ageix" / "evidence_packages" / smoke.package_id).exists()
    assert (tmp_path / ".ageix" / "evidence_packages" / real.package_id).exists()

    result = EvidencePackageCleanupService(tmp_path).cleanup_smoke_demo_packages(dry_run=False)

    assert result["deleted_package_ids"] == [smoke.package_id]
    assert not (tmp_path / ".ageix" / "evidence_packages" / smoke.package_id).exists()
    assert (tmp_path / ".ageix" / "evidence_packages" / real.package_id / "package.json").exists()
    entries = EvidencePackageIndexService(tmp_path).list_entries()
    ids = {entry["package_id"] for entry in entries}
    assert real.package_id in ids
    assert smoke.package_id not in ids
    assert result["validation_after"]["status"] == "pass"


def test_index_validation_reports_missing_dirs_and_invalid_parent_refs_without_repair(tmp_path: Path):
    parent = _package(tmp_path)
    child = _package(tmp_path)
    child.parent_package_ids = [parent.package_id, "EVPKG-MISSINGPARENT"]
    child.lineage_type = PackageLineageType.REUSE
    child_path = tmp_path / ".ageix" / "evidence_packages" / child.package_id / "package.json"
    child_path.write_text(child.model_dump_json(indent=2), encoding="utf-8")
    index = EvidencePackageIndexService(tmp_path)
    index.upsert_package(child)

    missing_dir = tmp_path / ".ageix" / "evidence_packages" / parent.package_id
    for file in missing_dir.glob("*"):
        file.unlink()
    missing_dir.rmdir()

    validation = index.validate_index()

    assert validation["status"] == "fail"
    assert parent.package_id in validation["missing_package_dirs"]
    assert {"package_id": child.package_id, "parent_package_id": "EVPKG-MISSINGPARENT"} in validation["invalid_parent_refs"]
    assert not (tmp_path / ".ageix" / "evidence_packages" / parent.package_id).exists()


def test_index_rebuild_treats_package_store_as_source_of_truth(tmp_path: Path):
    keep = _package(tmp_path)
    remove = _package(tmp_path)
    remove_dir = tmp_path / ".ageix" / "evidence_packages" / remove.package_id
    for file in remove_dir.glob("*"):
        file.unlink()
    remove_dir.rmdir()

    rebuilt = EvidencePackageIndexService(tmp_path).rebuild_from_package_store()

    ids = {entry["package_id"] for entry in rebuilt["packages"]}
    assert keep.package_id in ids
    assert remove.package_id not in ids
    assert EvidencePackageIndexService(tmp_path).validate_index()["status"] == "pass"
