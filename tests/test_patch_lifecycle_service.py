import json
from pathlib import Path

from services.patch_lifecycle_service import PatchLifecycleService


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_current_state_uses_highest_lifecycle_artifact(tmp_path):
    patch_id = "patch_1"

    write_json(tmp_path / ".ageix" / "manifests" / f"{patch_id}.json", {"patch_id": patch_id, "status": "staged"})
    assert PatchLifecycleService(tmp_path).current_state(patch_id) == "staged"

    write_json(tmp_path / ".ageix" / "verification" / "verification_1" / "report.json", {"patch_id": patch_id})
    assert PatchLifecycleService(tmp_path).current_state(patch_id) == "validated"

    write_json(tmp_path / ".ageix" / "approvals" / "approval_1" / "approval.json", {"patch_id": patch_id})
    assert PatchLifecycleService(tmp_path).current_state(patch_id) == "approved"

    write_json(tmp_path / ".ageix" / "promotions" / "promotion_1" / "promotion.json", {"patch_id": patch_id})
    assert PatchLifecycleService(tmp_path).current_state(patch_id) == "promoted"

    write_json(tmp_path / ".ageix" / "commits" / "commit_1" / "commit.json", {"patch_id": patch_id})
    assert PatchLifecycleService(tmp_path).current_state(patch_id) == "committed"


def test_current_state_unknown_when_no_artifacts_exist(tmp_path):
    assert PatchLifecycleService(tmp_path).current_state("missing_patch") == "unknown"
