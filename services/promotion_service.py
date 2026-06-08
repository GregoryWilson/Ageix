from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PromotionService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.stage_root = self.repo_root / ".ageix" / "staged"
        self.manifest_root = self.repo_root / ".ageix" / "manifests"

    def _safe_repo_path(self, relative_path: str) -> Path:
        candidate = (self.repo_root / relative_path).resolve()

        if not candidate.is_relative_to(self.repo_root):
            raise ValueError(f"Path escapes repository root: {relative_path}")

        return candidate

    def _manifest_path(self, patch_id: str) -> Path:
        return self.manifest_root / f"{patch_id}.json"

    def _stage_files_path(self, patch_id: str) -> Path:
        return self.stage_root / patch_id / "files"

    def _load_manifest(self, patch_id: str) -> dict[str, Any]:
        path = self._manifest_path(patch_id)

        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        return json.loads(path.read_text(encoding="utf-8"))

    def _save_manifest(self, patch_id: str, manifest: dict[str, Any]) -> None:
        path = self._manifest_path(patch_id)
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def approve_patch(self, patch_id: str, approved_by: str = "human") -> dict[str, Any]:
        manifest = self._load_manifest(patch_id)

        if manifest.get("status") not in {"staged", "tested"}:
            raise ValueError(f"Patch is not approvable from status: {manifest.get('status')}")

        manifest["status"] = "approved"
        manifest["approved_by"] = approved_by
        manifest["approved_at"] = datetime.now(timezone.utc).isoformat()

        self._save_manifest(patch_id, manifest)
        return manifest

    def promote_patch(self, patch_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(patch_id)

        if manifest.get("status") != "approved":
            raise ValueError("Patch must be approved before promotion.")

        stage_files_path = self._stage_files_path(patch_id)

        if not stage_files_path.exists():
            raise FileNotFoundError(f"Staged files not found: {stage_files_path}")

        promoted_files: list[str] = []

        for file_entry in manifest.get("files", []):
            relative_path = file_entry["path"]
            operation = file_entry["operation"]

            repo_path = self._safe_repo_path(relative_path)
            staged_path = stage_files_path / relative_path

            if operation in {"create", "modify"}:
                if not staged_path.exists():
                    raise FileNotFoundError(f"Missing staged file: {staged_path}")

                repo_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_path, repo_path)
                promoted_files.append(relative_path)

            elif operation == "delete":
                if repo_path.exists():
                    repo_path.unlink()
                promoted_files.append(relative_path)

            else:
                raise ValueError(f"Unsupported file operation: {operation}")

        manifest["status"] = "promoted"
        manifest["promoted_at"] = datetime.now(timezone.utc).isoformat()
        manifest["promoted_files"] = promoted_files

        self._save_manifest(patch_id, manifest)
        return manifest
    
    def commit_promoted_patch(self, patch_id: str, message: str | None = None) -> dict[str, Any]:
        manifest = self._load_manifest(patch_id)

        if manifest.get("status") != "promoted":
            raise ValueError("Patch must be promoted before commit.")

        promoted_files = manifest.get("promoted_files", [])

        if not promoted_files:
            raise ValueError("No promoted files found in manifest.")

        commit_message = message or f"Apply staged patch {patch_id}"

        commit_hash = self.git.commit_paths(
            message=commit_message,
            paths=promoted_files,
        )

        manifest["status"] = "committed"
        manifest["git_commit"] = commit_hash
        manifest["committed_at"] = datetime.now(timezone.utc).isoformat()

        self._save_manifest(patch_id, manifest)
        return manifest