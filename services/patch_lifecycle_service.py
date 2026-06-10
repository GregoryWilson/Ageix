from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PatchLifecycleService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.ageix_root = self.repo_root / ".ageix"

    def current_state(self, patch_id: str) -> str:
        if self.is_committed(patch_id):
            return "committed"
        if self.is_promoted(patch_id):
            return "promoted"
        if self.is_approved(patch_id):
            return "approved"
        if self.is_validated(patch_id):
            return "validated"
        if self.is_staged(patch_id):
            return "staged"
        if self.is_proposed(patch_id):
            return "proposed"
        return "unknown"

    def is_proposed(self, patch_id: str) -> bool:
        return self._artifact_contains_patch_id(self.ageix_root / "proposals", patch_id)

    def is_staged(self, patch_id: str) -> bool:
        return (self.ageix_root / "staged" / patch_id).exists() or self._manifest_has_status(
            patch_id, {"staged", "validated", "approved", "promoted", "committed"}
        )

    def is_validated(self, patch_id: str) -> bool:
        return self._artifact_contains_patch_id(self.ageix_root / "verification", patch_id)

    def is_approved(self, patch_id: str) -> bool:
        return self._artifact_contains_patch_id(self.ageix_root / "approvals", patch_id)

    def is_promoted(self, patch_id: str) -> bool:
        return self._artifact_contains_patch_id(self.ageix_root / "promotions", patch_id)

    def is_committed(self, patch_id: str) -> bool:
        return self._artifact_contains_patch_id(self.ageix_root / "commits", patch_id)

    def _manifest_has_status(self, patch_id: str, statuses: set[str]) -> bool:
        path = self.ageix_root / "manifests" / f"{patch_id}.json"

        if not path.exists():
            return False

        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

        return manifest.get("status") in statuses

    def _artifact_contains_patch_id(self, directory: Path, patch_id: str) -> bool:
        if not directory.exists():
            return False

        for path in directory.rglob("*.json"):
            try:
                payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if payload.get("patch_id") == patch_id:
                return True

        return False
