from services.cloud_repair_context_builder import CloudRepairContextBuilder


def test_cloud_repair_context_builder_preserves_core_ids_and_summarizes_attempts():
    builder = CloudRepairContextBuilder()

    packet = builder.build_packet(
        repair_loop_manifest={
            "repair_loop_id": "repair_loop_1",
            "origin_verification_id": "verification_origin",
            "origin_patch_id": "patch_origin",
            "objective": "Fix failing test.",
            "attempts": [
                {
                    "attempt_number": 1,
                    "repair_patch_id": "patch_1",
                    "verification_id": "verification_1",
                    "validation_result": "FAIL",
                    "decision": "retry",
                    "changed_files": ["foo.py"],
                }
            ],
        },
        repository_evidence={"evidence": [{"path": "foo.py", "summary": "Relevant file"}]},
        latest_validation_report={
            "verification_id": "verification_1",
            "patch_id": "patch_1",
            "result": "FAIL",
            "stderr": "AssertionError: expected 1 got 2",
        },
    )

    assert packet["origin_verification_id"] == "verification_origin"
    assert packet["origin_patch_id"] == "patch_origin"
    assert packet["objective"] == "Fix failing test."
    assert packet["local_attempt_count"] == 1
    assert packet["local_repair_history"][0]["source"] == "local"
    assert packet["latest_validation_failure"]["result"] == "FAIL"
    assert packet["repository_evidence"][0]["path"] == "foo.py"


import json
from pathlib import Path

from services.cloud_repair_context_builder import CloudRepairContextBuilder


def test_cloud_context_builder_uses_controls_limits(tmp_path: Path):
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)

    (config_dir / "controls.json").write_text(
        json.dumps(
            {
                "cloud": {
                    "max_evidence_items": 2,
                    "max_failure_summary_chars": 10,
                }
            }
        ),
        encoding="utf-8",
    )

    builder = CloudRepairContextBuilder(repo_root=tmp_path)

    packet = builder.build_packet(
        repair_loop_manifest={
            "repair_loop_id": "repair_loop_test",
            "origin_verification_id": "verification_origin",
            "origin_patch_id": "patch_origin",
            "attempts": [],
        },
        repository_evidence=[
            {"file": "one.py"},
            {"file": "two.py"},
            {"file": "three.py"},
        ],
        latest_validation_report={
            "verification_id": "verification_fail",
            "patch_id": "patch_fail",
            "result": "FAIL",
            "error_output": "abcdefghijklmnopqrstuvwxyz",
        },
    )

    assert len(packet["repository_evidence"]) == 2
    assert packet["latest_validation_failure"]["summary"] == "abcdefghij"
    assert packet["latest_validation_failure"]["truncated"] is True