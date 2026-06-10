from pathlib import Path

import pytest

from services.patch_lineage_service import PatchLineageService


def test_records_repair_relationship(tmp_path: Path):
    svc = PatchLineageService(tmp_path)

    relationship = svc.record_repair_relationship(
        parent_patch_id="patch_1",
        child_patch_id="patch_2",
        source_verification_id="verification_1",
        repair_loop_id="repair_loop_1",
    )

    assert relationship["parent_patch_id"] == "patch_1"
    assert relationship["child_patch_id"] == "patch_2"
    assert relationship["relationship_type"] == "repair"
    assert list((tmp_path / ".ageix" / "lineage" / "relationships").rglob("relationship.json"))


def test_records_cloud_escalation_relationship(tmp_path: Path):
    svc = PatchLineageService(tmp_path)

    relationship = svc.record_cloud_escalation_relationship(
        parent_patch_id="patch_2",
        child_patch_id="patch_3",
        source_verification_id="verification_2",
        repair_loop_id="repair_loop_1",
    )

    assert relationship["relationship_type"] == "cloud_escalation"


def test_rejects_invalid_relationship_type(tmp_path: Path):
    svc = PatchLineageService(tmp_path)

    with pytest.raises(ValueError):
        svc.record_patch_relationship("patch_1", "patch_2", "nonsense")


def test_finds_root_patch(tmp_path: Path):
    svc = PatchLineageService(tmp_path)
    svc.record_repair_relationship("patch_1", "patch_2")
    svc.record_cloud_escalation_relationship("patch_2", "patch_3")

    assert svc.find_root_patch("patch_3") == "patch_1"


def test_builds_lineage_graph(tmp_path: Path):
    svc = PatchLineageService(tmp_path)
    svc.record_repair_relationship("patch_1", "patch_2")
    svc.record_cloud_escalation_relationship("patch_2", "patch_3")
    svc.record_verification_relationship("patch_1", "verification_1", "FAIL")
    svc.record_verification_relationship("patch_2", "verification_2", "FAIL")
    svc.record_verification_relationship("patch_3", "verification_3", "PASS")
    svc.record_commit_relationship("patch_3", "commit_record_1", git_commit="abc123", promotion_id="promotion_1")

    graph = svc.build_lineage_graph("patch_3")

    assert graph["root_patch_id"] == "patch_1"
    assert graph["requested_patch_id"] == "patch_3"
    assert graph["patch_ids"] == ["patch_1", "patch_2", "patch_3"]
    assert len(graph["patch_relationships"]) == 2
    assert len(graph["lifecycle_relationships"]) == 4


def test_lineage_metrics(tmp_path: Path):
    svc = PatchLineageService(tmp_path)
    svc.record_repair_relationship("patch_1", "patch_2")
    svc.record_cloud_escalation_relationship("patch_2", "patch_3")
    svc.record_verification_relationship("patch_1", "verification_1", "FAIL")
    svc.record_verification_relationship("patch_2", "verification_2", "FAIL")
    svc.record_verification_relationship("patch_3", "verification_3", "PASS")
    svc.record_commit_relationship("patch_3", "commit_record_1", git_commit="abc123")

    metrics = svc.get_lineage_metrics("patch_3")

    assert metrics == {
        "repair_attempts": 1,
        "cloud_escalations": 1,
        "verification_failures": 2,
        "verification_passes": 1,
        "commits": 1,
    }


def test_explain_patch_contains_ancestry_and_metrics(tmp_path: Path):
    svc = PatchLineageService(tmp_path)
    svc.record_repair_relationship("patch_1", "patch_2")
    svc.record_cloud_escalation_relationship("patch_2", "patch_3")
    svc.record_verification_relationship("patch_3", "verification_3", "PASS")
    svc.record_commit_relationship("patch_3", "commit_record_1", git_commit="abc123")

    explanation = svc.explain_patch("patch_3")

    assert "Origin: patch_1" in explanation
    assert "patch_1 -> patch_2 (repair)" in explanation
    assert "patch_2 -> patch_3 (cloud_escalation)" in explanation
    assert "verification verification_3 (PASS)" in explanation
    assert "commit record commit_record_1 (abc123)" in explanation
