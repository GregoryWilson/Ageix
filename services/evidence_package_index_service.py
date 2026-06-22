from __future__ import annotations

import json
from pathlib import Path

from models.evidence_package import EvidencePackage, EvidencePackageIndexEntry, PackageFreshness, PackageFreshnessStatus


class EvidencePackageIndexService:
    """Maintains the package discovery index without mutating package contents."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "evidence_packages" / "index.json"

    def upsert_package(self, package: EvidencePackage) -> EvidencePackageIndexEntry:
        freshness = package.freshness or PackageFreshness()
        entry = EvidencePackageIndexEntry(
            package_id=package.package_id,
            proposal_id=package.proposal_id,
            evidence_plan_id=package.evidence_plan_id,
            objective=package.objective,
            created_at=package.created_at,
            retrieval_confidence=package.retrieval_confidence,
            primary_count=len(package.primary_evidence),
            supporting_count=len(package.supporting_evidence),
            validation_count=len(package.validation_evidence),
            coverage_gap_count=len(package.coverage_gaps),
            freshness_status=freshness.status,
            stale=freshness.stale,
            last_freshness_check_at=freshness.last_freshness_check_at,
        )
        data = self._load()
        entries = [item for item in data.get("packages", []) if item.get("package_id") != package.package_id]
        entries.append(entry.model_dump())
        entries.sort(key=lambda item: item.get("created_at", ""))
        self._write({"schema_version": 1, "packages": entries})
        return entry

    def update_freshness(self, package: EvidencePackage, freshness: PackageFreshness) -> EvidencePackageIndexEntry:
        clone = package.model_copy(deep=True)
        clone.freshness = freshness
        return self.upsert_package(clone)

    def list_entries(self) -> list[dict]:
        return list(self._load().get("packages", []))

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "packages": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
