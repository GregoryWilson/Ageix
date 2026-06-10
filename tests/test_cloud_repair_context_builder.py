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