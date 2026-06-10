import json
from pathlib import Path

import pytest

from services.promotion_service import PromotionService


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_approve_patch_records_approval_artifact(tmp_path):
    patch_id = "patch_1"
    verification_id = "verification_1"

    write_json(tmp_path / ".ageix" / "manifests" / f"{patch_id}.json", {"patch_id": patch_id, "status": "staged"})
    write_json(
        tmp_path / ".ageix" / "verification" / verification_id / "report.json",
        {"verification_id": verification_id, "patch_id": patch_id, "result": "PASS"},
    )

    approval = PromotionService(tmp_path).approve_patch(patch_id, verification_id)

    approval_path = tmp_path / ".ageix" / "approvals" / approval["approval_id"] / "approval.json"
    assert approval_path.exists()
    assert approval["approved_by"] == "human"
    assert approval["patch_id"] == patch_id


def test_promote_patch_records_promotion_artifact_without_modifying_repo(tmp_path):
    patch_id = "patch_1"
    verification_id = "verification_1"
    approval_id = "approval_1"
    live_file = tmp_path / "scratch" / "example.txt"
    live_file.parent.mkdir(parents=True)
    live_file.write_text("original", encoding="utf-8")

    write_json(tmp_path / ".ageix" / "manifests" / f"{patch_id}.json", {"patch_id": patch_id, "status": "approved"})
    write_json(
        tmp_path / ".ageix" / "approvals" / approval_id / "approval.json",
        {"approval_id": approval_id, "patch_id": patch_id, "verification_id": verification_id, "approved_by": "human"},
    )
    staged_file = tmp_path / ".ageix" / "staged" / patch_id / "files" / "scratch" / "example.txt"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_text("patched", encoding="utf-8")

    promotion = PromotionService(tmp_path).promote_patch(patch_id, verification_id, approval_id)

    assert promotion["status"] == "promoted"
    assert live_file.read_text(encoding="utf-8") == "original"
    assert (tmp_path / ".ageix" / "promotions" / promotion["promotion_id"] / "promotion.json").exists()


def test_autonomous_promotion_is_denied_by_governance(tmp_path):
    patch_id = "patch_1"
    verification_id = "verification_1"
    approval_id = "approval_1"

    write_json(tmp_path / ".ageix" / "manifests" / f"{patch_id}.json", {"patch_id": patch_id, "status": "approved"})
    write_json(
        tmp_path / ".ageix" / "approvals" / approval_id / "approval.json",
        {"approval_id": approval_id, "patch_id": patch_id, "verification_id": verification_id, "approved_by": "human"},
    )

    result = PromotionService(tmp_path).promote_patch(
        patch_id,
        verification_id,
        approval_id,
        requested_by="ageix",
    )

    assert result["status"] == "human_review_required"
    assert not (tmp_path / ".ageix" / "promotions").exists()


def test_commit_patch_records_commit_metadata_only(tmp_path):
    patch_id = "patch_1"
    promotion_id = "promotion_1"

    write_json(tmp_path / ".ageix" / "manifests" / f"{patch_id}.json", {"patch_id": patch_id, "status": "promoted"})
    write_json(
        tmp_path / ".ageix" / "promotions" / promotion_id / "promotion.json",
        {"promotion_id": promotion_id, "patch_id": patch_id, "status": "promoted"},
    )

    commit = PromotionService(tmp_path).commit_patch(
        patch_id=patch_id,
        git_commit="abc123",
        promotion_id=promotion_id,
    )

    assert commit["git_commit"] == "abc123"
    assert commit["committed_by"] == "human"
    assert (tmp_path / ".ageix" / "commits" / commit["commit_record_id"] / "commit.json").exists()


def test_commit_patch_rejects_non_human_commit_record(tmp_path):
    with pytest.raises(PermissionError):
        PromotionService(tmp_path).commit_patch(
            patch_id="patch_1",
            git_commit="abc123",
            promotion_id="promotion_1",
            committed_by="ageix",
        )
