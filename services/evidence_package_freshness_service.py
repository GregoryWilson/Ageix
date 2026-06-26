from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from models.evidence_package import EvidencePackage, PackageFreshness, PackageFreshnessStatus
from services.evidence_package_index_service import EvidencePackageIndexService
from services.evidence_retrieval_guard_service import EvidenceRetrievalGuardService


class EvidencePackageFreshnessService:
    """Evaluates substantive content drift for immutable evidence packages."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.guard = EvidenceRetrievalGuardService(self.repo_root)
        self.index = EvidencePackageIndexService(self.repo_root)

    def evaluate(self, package: EvidencePackage) -> PackageFreshness:
        missing: list[str] = []
        changed: list[str] = []
        unchanged: list[str] = []
        for item in package.all_evidence():
            decision = self.guard.evaluate(item.path)
            full = self.repo_root / item.path
            if not full.exists() or not full.is_file():
                missing.append(item.path)
                continue
            if not decision.allowed:
                missing.append(item.path)
                continue
            current_hash = self.hash_path(full)
            if item.content_hash and current_hash == item.content_hash:
                unchanged.append(item.path)
            else:
                changed.append(item.path)
        if missing and len(missing) == len(package.all_evidence()):
            status = PackageFreshnessStatus.MISSING
        elif missing:
            status = PackageFreshnessStatus.PARTIALLY_MISSING
        elif changed:
            status = PackageFreshnessStatus.MODIFIED
        else:
            status = PackageFreshnessStatus.UNCHANGED
        stale = status != PackageFreshnessStatus.UNCHANGED
        reason = self._reason(status)
        freshness = PackageFreshness(
            status=status,
            stale=stale,
            freshness_reason=reason,
            missing_paths=missing,
            changed_paths=changed,
            unchanged_paths=unchanged,
            last_freshness_check_at=datetime.now(timezone.utc).isoformat(),
        )
        self.index.update_freshness(package, freshness)
        return freshness

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def hash_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _reason(self, status: PackageFreshnessStatus) -> str:
        if status == PackageFreshnessStatus.UNCHANGED:
            return "Package evidence still matches the current repository content."
        if status == PackageFreshnessStatus.MODIFIED:
            return "One or more evidence files have substantively changed since the package was created."
        if status == PackageFreshnessStatus.PARTIALLY_MISSING:
            return "One or more evidence files are missing from the current repository state."
        if status == PackageFreshnessStatus.MISSING:
            return "All evidence files are missing from the current repository state."
        return "Freshness evaluation failed."
