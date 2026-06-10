from __future__ import annotations

import json
from pathlib import Path

from services.repair_intelligence_service import RepairIntelligenceService


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_record_repair_outcome_creates_artifact(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    result = service.record_repair_outcome(
        patch_id="patch_1",
        result="PASS",
        repair_attempts=2,
        files_modified=["services/router.py"],
        successful_strategy="local_repair",
    )

    path = tmp_path / ".ageix" / "repair_intelligence" / "outcomes" / "patch_1" / "repair_intelligence.json"
    assert path.exists()
    assert result["patch_id"] == "patch_1"
    assert read_json(path)["files_modified"] == ["services/router.py"]


def test_record_repair_outcome_rejects_invalid_result(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    try:
        service.record_repair_outcome(patch_id="patch_1", result="MAYBE")
    except ValueError as exc:
        assert "PASS or FAIL" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_statistics_track_success_failure_and_average_attempts(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    service.record_repair_outcome("patch_1", "PASS", repair_attempts=1, files_modified=["a.py"])
    service.record_repair_outcome("patch_2", "PASS", repair_attempts=3, files_modified=["b.py"])
    service.record_repair_outcome("patch_3", "FAIL", repair_attempts=2, files_modified=["b.py"], failure_type="test_failure")

    stats = service.get_patch_statistics()

    assert stats["total_repairs"] == 3
    assert stats["successful_repairs"] == 2
    assert stats["failed_repairs"] == 1
    assert stats["average_attempts_before_success"] == 2.0


def test_cloud_escalation_success_rate(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    service.record_cloud_escalation("patch_1", "PASS")
    service.record_cloud_escalation("patch_2", "FAIL", failure_type="cloud_patch_failed")
    service.record_repair_outcome("patch_3", "PASS")

    stats = service.get_patch_statistics()

    assert stats["cloud_escalations"] == 2
    assert stats["cloud_escalation_success_rate"] == 0.5


def test_hotspots_identify_repeated_files(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    service.record_repair_outcome("patch_1", "PASS", files_modified=["services/router.py"])
    service.record_repair_outcome("patch_2", "FAIL", files_modified=["services/router.py", "services/chair.py"])
    service.record_repair_outcome("patch_3", "PASS", files_modified=["services/chair.py"])
    service.record_repair_outcome("patch_4", "PASS", files_modified=["services/router.py"])

    hotspots = service.get_hotspots()

    assert hotspots["services/router.py"] == 3
    assert hotspots["services/chair.py"] == 2


def test_failure_and_success_patterns(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    service.record_repair_outcome("patch_1", "FAIL", failure_type="validation_failure")
    service.record_repair_outcome("patch_2", "FAIL", failure_type="validation_failure")
    service.record_repair_outcome("patch_3", "PASS", successful_strategy="cloud_escalation")

    assert service.get_failure_patterns()["validation_failure"] == 2
    assert service.get_success_patterns()["cloud_escalation"] == 1


def test_explain_failure_pattern_for_file(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    service.record_repair_outcome(
        "patch_1",
        "FAIL",
        files_modified=["services/router.py"],
        failure_type="validation_failure",
    )
    service.record_repair_outcome(
        "patch_2",
        "PASS",
        files_modified=["services/router.py"],
        successful_strategy="cloud_escalation",
    )

    explanation = service.explain_failure_pattern("services/router.py")

    assert "services/router.py has participated in 2 repairs" in explanation
    assert "Most common failure: validation_failure" in explanation
    assert "Most common successful strategy: cloud_escalation" in explanation


def test_record_commit_success_links_commit_metadata(tmp_path):
    service = RepairIntelligenceService(tmp_path)

    result = service.record_commit_success(
        patch_id="patch_1",
        commit_record_id="commit_record_1",
        git_commit="abc123",
        files_modified=["services/router.py"],
    )

    assert result["result"] == "PASS"
    assert result["successful_strategy"] == "human_commit"
    assert result["metadata"]["git_commit"] == "abc123"
