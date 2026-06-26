from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from models.evidence_package import EvidencePackage
from services.evidence_package_index_service import EvidencePackageIndexService


class EvidencePackageCleanupService:
    """Conservative cleanup for explicitly marked smoke-demo evidence packages."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.package_root = self.repo_root / ".ageix" / "evidence_packages"
        self.index = EvidencePackageIndexService(self.repo_root)

    def cleanup_smoke_demo_packages(self, *, dry_run: bool = True) -> dict[str, Any]:
        candidates = self.find_smoke_demo_packages()
        validation_before = self.index.validate_index()
        deleted: list[str] = []
        for candidate in candidates:
            if dry_run:
                continue
            shutil.rmtree(candidate["package_dir"])
            deleted.append(candidate["package_id"])
        rebuilt = None
        validation_after = validation_before
        if not dry_run:
            rebuilt = self.index.rebuild_from_package_store()
            validation_after = self.index.validate_index()
        return {
            "dry_run": dry_run,
            "candidate_count": len(candidates),
            "candidates": [self._public_candidate(candidate) for candidate in candidates],
            "deleted_package_ids": deleted,
            "deleted_count": len(deleted),
            "index_rebuilt": not dry_run,
            "rebuilt_package_count": rebuilt.get("package_count") if rebuilt else None,
            "validation_before": validation_before,
            "validation_after": validation_after,
        }

    def find_smoke_demo_packages(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if not self.package_root.exists():
            return candidates
        for package_file in sorted(self.package_root.glob("EVPKG-*/package.json")):
            try:
                package = EvidencePackage(**json.loads(package_file.read_text(encoding="utf-8")))
            except Exception:
                continue
            lifecycle = dict(package.lifecycle or {})
            if lifecycle.get("artifact_type") != "smoke_demo":
                continue
            candidates.append({
                "package_id": package.package_id,
                "package_dir": package_file.parent,
                "package_path": package_file,
                "objective": package.objective,
                "created_at": package.created_at,
                "lifecycle": lifecycle,
            })
        return candidates

    def _public_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "package_id": candidate["package_id"],
            "package_path": str(candidate["package_path"].relative_to(self.repo_root)),
            "objective": candidate["objective"],
            "created_at": candidate["created_at"],
            "lifecycle": candidate["lifecycle"],
        }
