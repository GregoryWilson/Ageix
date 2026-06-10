from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.repair_loop_service import RepairLoopService


class FakeRepairExecutionService:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = list(results)
        self.calls: list[str] = []

    def execute_repair_cycle(self, verification_id: str) -> dict[str, Any]:
        self.calls.append(verification_id)
        return self.results.pop(0)


def write_verification(
    repo_root: Path,
    verification_id: str,
    patch_id: str,
    result: str,
) -> None:
    verification_dir = repo_root / ".ageix" / "verification" / verification_id
    verification_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "verification_id": verification_id,
        "patch_id": patch_id,
        "status": "materialized",
        "result": result,
        "reasoning": [],
    }

    (verification_dir / "report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )


def test_repair_loop_first_attempt_passes(tmp_path: Path) -> None:
    write_verification(tmp_path, "verification_origin", "patch_origin", "FAIL")
    write_verification(tmp_path, "verification_repair_1", "patch_repair_1", "PASS")

    fake_executor = FakeRepairExecutionService(
        results=[
            {
                "repair_patch_id": "patch_repair_1",
                "repair_verification_id": "verification_repair_1",
            }
        ],
    )

    service = RepairLoopService(
        repo_root=tmp_path,
        repair_execution_service=fake_executor,
    )

    manifest = service.run_repair_loop(
        origin_verification_id="verification_origin",
        max_attempts=3,
    )

    assert manifest["origin_patch_id"] == "patch_origin"
    assert manifest["origin_verification_id"] == "verification_origin"
    assert manifest["final_action"] == "human_review"
    assert len(manifest["attempts"]) == 1
    assert manifest["attempts"][0]["validation_result"] == "PASS"
    assert manifest["attempts"][0]["decision"] == "human_review"
    assert fake_executor.calls == ["verification_origin"]


def test_repair_loop_retries_then_passes(tmp_path: Path) -> None:
    write_verification(tmp_path, "verification_origin", "patch_origin", "FAIL")
    write_verification(tmp_path, "verification_repair_1", "patch_repair_1", "FAIL")
    write_verification(tmp_path, "verification_repair_2", "patch_repair_2", "PASS")

    fake_executor = FakeRepairExecutionService(
        results=[
            {
                "repair_patch_id": "patch_repair_1",
                "repair_verification_id": "verification_repair_1",
            },
            {
                "repair_patch_id": "patch_repair_2",
                "repair_verification_id": "verification_repair_2",
            },
        ],
    )

    service = RepairLoopService(
        repo_root=tmp_path,
        repair_execution_service=fake_executor,
    )

    manifest = service.run_repair_loop(
        origin_verification_id="verification_origin",
        max_attempts=3,
    )

    assert manifest["final_action"] == "human_review"
    assert len(manifest["attempts"]) == 2
    assert manifest["attempts"][0]["decision"] == "continue_repair"
    assert manifest["attempts"][1]["decision"] == "human_review"
    assert fake_executor.calls == [
        "verification_origin",
        "verification_repair_1",
    ]


def test_repair_loop_escalates_after_max_attempts_then_routes_to_human_review(
    tmp_path: Path,
) -> None:
    write_verification(tmp_path, "verification_origin", "patch_origin", "FAIL")
    write_verification(tmp_path, "verification_repair_1", "patch_repair_1", "FAIL")
    write_verification(tmp_path, "verification_repair_2", "patch_repair_2", "FAIL")
    write_verification(tmp_path, "verification_repair_3", "patch_repair_3", "FAIL")

    fake_executor = FakeRepairExecutionService(
        results=[
            {
                "repair_patch_id": "patch_repair_1",
                "repair_verification_id": "verification_repair_1",
            },
            {
                "repair_patch_id": "patch_repair_2",
                "repair_verification_id": "verification_repair_2",
            },
            {
                "repair_patch_id": "patch_repair_3",
                "repair_verification_id": "verification_repair_3",
            },
        ],
    )

    service = RepairLoopService(
        repo_root=tmp_path,
        repair_execution_service=fake_executor,
    )

    manifest = service.run_repair_loop(
        origin_verification_id="verification_origin",
        max_attempts=3,
    )

    assert manifest["status"] == "complete"
    assert manifest["final_action"] == "human_review"
    assert manifest["escalation"]["recorded_action"] == "escalate_repair"
    assert manifest["escalation"]["routed_to"] == "human_review"
    assert len(manifest["attempts"]) == 3
    assert manifest["attempts"][-1]["decision"] == "escalate_repair"
    assert fake_executor.calls == [
        "verification_origin",
        "verification_repair_1",
        "verification_repair_2",
    ]


def test_repair_loop_persists_manifest(tmp_path: Path) -> None:
    write_verification(tmp_path, "verification_origin", "patch_origin", "FAIL")
    write_verification(tmp_path, "verification_repair_1", "patch_repair_1", "PASS")

    fake_executor = FakeRepairExecutionService(
        results=[
            {
                "repair_patch_id": "patch_repair_1",
                "repair_verification_id": "verification_repair_1",
            }
        ],
    )

    service = RepairLoopService(
        repo_root=tmp_path,
        repair_execution_service=fake_executor,
    )

    manifest = service.run_repair_loop(
        origin_verification_id="verification_origin",
        max_attempts=3,
    )

    manifest_path = (
        tmp_path
        / ".ageix"
        / "repair_loops"
        / manifest["repair_loop_id"]
        / "manifest.json"
    )

    assert manifest_path.exists()

    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert persisted == manifest