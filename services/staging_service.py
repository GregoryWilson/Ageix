from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from models.patch_manifest import PatchFile, PatchManifest
from models.patch_proposal import PatchProposal


class StagingService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.stage_root = self.repo_root / ".ageix" / "staged"
        self.manifest_root = self.repo_root / ".ageix" / "manifests"

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _safe_repo_path(self, relative_path: str) -> Path:
        candidate = (self.repo_root / relative_path).resolve()

        if not candidate.is_relative_to(self.repo_root):
            raise ValueError(f"Path escapes repository root: {relative_path}")

        return candidate

    def create_patch_id(self) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"patch_{timestamp}"

    def create_stage(
        self,
        *,
        files: list[str],
        summary: str,
        created_by: str = "dev_worker",
        conversation_id: str | None = None,
        work_order_id: str | None = None,
        evidence_sources: list[str] | None = None,
    ) -> PatchManifest:
        patch_id = self.create_patch_id()
        patch_dir = self.stage_root / patch_id / "files"
        patch_dir.mkdir(parents=True, exist_ok=False)

        manifest_files: list[PatchFile] = []

        for relative_path in files:
            source_path = self._safe_repo_path(relative_path)
            staged_path = patch_dir / relative_path
            staged_path.parent.mkdir(parents=True, exist_ok=True)

            if source_path.exists():
                shutil.copy2(source_path, staged_path)
                operation = "modify"
                original_hash = self._hash_file(source_path)
                staged_hash = self._hash_file(staged_path)
            else:
                staged_path.touch()
                operation = "create"
                original_hash = None
                staged_hash = self._hash_file(staged_path)

            manifest_files.append(
                PatchFile(
                    path=relative_path,
                    operation=operation,
                    original_hash=original_hash,
                    staged_hash=staged_hash,
                )
            )

        manifest = PatchManifest(
            patch_id=patch_id,
            status="staged",
            summary=summary,
            created_by=created_by,
            conversation_id=conversation_id,
            work_order_id=work_order_id,
            files=manifest_files,
            evidence_sources=evidence_sources or [],
        )

        self.manifest_root.mkdir(parents=True, exist_ok=True)

        manifest.save(self.manifest_root / f"{patch_id}.json")
        manifest.save(self.stage_root / patch_id / "manifest.json")

        return manifest

    def get_stage_path(self, patch_id: str) -> Path:
        return self.stage_root / patch_id / "files"

    def get_manifest_path(self, patch_id: str) -> Path:
        return self.manifest_root / f"{patch_id}.json"
    
    def create_stage_from_patch_proposal(
        self,
        proposal: dict,
    ) -> PatchManifest:
        changes = proposal.get("changes", [])

        files = [
            change["path"]
            for change in changes
        ]

        manifest = self.create_stage(
            files=files,
            summary=proposal.get("summary", "DevWorker patch proposal"),
            created_by="dev_worker",
            evidence_sources=[
                evidence.get("path", "")
                for evidence in proposal.get("evidence_used", [])
                if evidence.get("path")
            ],
        )

        stage_path = self.get_stage_path(manifest.patch_id)

        for change in changes:
            operation = change.get("operation")

            if operation != "replace_file":
                raise ValueError(
                    f"Unsupported patch proposal operation: {operation}"
                )

            relative_path = change["path"]
            staged_file = stage_path / relative_path
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            staged_file.write_text(
                change["content"],
                encoding="utf-8",
            )

        # Important: update hashes after writing replacement contents
        for manifest_file in manifest.files:
            staged_file = stage_path / manifest_file.path
            manifest_file.staged_hash = self._hash_file(staged_file)

        manifest.save(self.get_manifest_path(manifest.patch_id))
        manifest.save(self.stage_root / manifest.patch_id / "manifest.json")

        return manifest