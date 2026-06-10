from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.governance_policy_service import GovernancePolicyService


class PromotionService:
    """Records patch approval, promotion, and commit lifecycle artifacts.

    This service is intentionally metadata-only. It must not copy files into the
    live repository and must not execute git commits.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.ageix_root = self.repo_root / ".ageix"
        self.manifest_root = self.ageix_root / "manifests"
        self.verification_root = self.ageix_root / "verification"
        self.approval_root = self.ageix_root / "approvals"
        self.promotion_root = self.ageix_root / "promotions"
        self.commit_root = self.ageix_root / "commits"
        self.governance = GovernancePolicyService(self.repo_root)

    def approve_patch(
        self,
        patch_id: str,
        verification_id: str,
        approved_by: str = "human",
        reason: str = "Validation successful",
    ) -> dict[str, Any]:
        if approved_by != "human":
            raise PermissionError("Only a human may approve a patch.")

        verification = self._load_verification(verification_id)

        if verification.get("patch_id") != patch_id:
            raise ValueError("Verification does not belong to the requested patch.")

        if verification.get("result") != "PASS":
            raise ValueError("Patch may only be approved after PASS validation.")

        approval_id = self._new_id("approval")
        approval = {
            "approval_id": approval_id,
            "patch_id": patch_id,
            "verification_id": verification_id,
            "approved_by": approved_by,
            "approved_timestamp": self._now(),
            "reason": reason,
        }

        self._write_artifact(self.approval_root / approval_id / "approval.json", approval)
        self._set_manifest_status(patch_id, "approved", approval_id=approval_id)
        return approval

    def promote_patch(
        self,
        patch_id: str,
        verification_id: str,
        approval_id: str,
        requested_by: str = "human",
    ) -> dict[str, Any]:
        approval = self._load_approval(approval_id)

        if approval.get("patch_id") != patch_id:
            raise ValueError("Approval does not belong to the requested patch.")

        if approval.get("verification_id") != verification_id:
            raise ValueError("Approval does not match the requested verification.")

        if requested_by != "human" and not self._may_promote_patch(patch_id):
            return {
                "status": "human_review_required",
                "patch_id": patch_id,
                "verification_id": verification_id,
                "approval_id": approval_id,
                "reason": "GovernancePolicyService denied autonomous promotion.",
            }

        promotion_id = self._new_id("promotion")
        promotion = {
            "promotion_id": promotion_id,
            "patch_id": patch_id,
            "verification_id": verification_id,
            "approval_id": approval_id,
            "status": "promoted",
            "promoted_by": requested_by,
            "promoted_timestamp": self._now(),
        }

        self._write_artifact(self.promotion_root / promotion_id / "promotion.json", promotion)
        self._set_manifest_status(patch_id, "promoted", promotion_id=promotion_id)
        return promotion

    def commit_patch(
        self,
        patch_id: str,
        git_commit: str,
        promotion_id: str,
        committed_by: str = "human",
    ) -> dict[str, Any]:
        if committed_by != "human":
            raise PermissionError("Only a human-performed commit may be recorded.")

        promotion = self._load_promotion(promotion_id)

        if promotion.get("patch_id") != patch_id:
            raise ValueError("Promotion does not belong to the requested patch.")

        commit_record_id = self._new_id("commit")
        commit_record = {
            "commit_record_id": commit_record_id,
            "patch_id": patch_id,
            "git_commit": git_commit,
            "promotion_id": promotion_id,
            "committed_by": committed_by,
            "timestamp": self._now(),
        }

        self._write_artifact(self.commit_root / commit_record_id / "commit.json", commit_record)
        self._set_manifest_status(
            patch_id,
            "committed",
            commit_record_id=commit_record_id,
            git_commit=git_commit,
        )
        return commit_record

    def _may_promote_patch(self, patch_id: str) -> bool:
        may_promote = getattr(self.governance, "may_promote_patch", None)

        if may_promote is None:
            return False

        return bool(may_promote())
    
    def _manifest_path(self, patch_id: str) -> Path:
        return self.manifest_root / f"{patch_id}.json"

    def _load_manifest(self, patch_id: str) -> dict[str, Any]:
        path = self._manifest_path(patch_id)

        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        return json.loads(path.read_text(encoding="utf-8"))

    def _set_manifest_status(self, patch_id: str, status: str, **extra: Any) -> None:
        path = self._manifest_path(patch_id)

        if not path.exists():
            return

        manifest = self._load_manifest(patch_id)
        manifest["status"] = status
        manifest.update(extra)
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _load_verification(self, verification_id: str) -> dict[str, Any]:
        return self._load_artifact(self.verification_root / verification_id / "report.json")

    def _load_approval(self, approval_id: str) -> dict[str, Any]:
        return self._load_artifact(self.approval_root / approval_id / "approval.json")

    def _load_promotion(self, promotion_id: str) -> dict[str, Any]:
        return self._load_artifact(self.promotion_root / promotion_id / "promotion.json")

    def _load_artifact(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")

        return json.loads(path.read_text(encoding="utf-8"))

    def _write_artifact(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
