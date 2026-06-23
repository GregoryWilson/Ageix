from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from models.evidence_package import EvidencePackage, EvidencePackageIndexEntry, PackageFreshness, PackageGovernanceMetadata, PackageGovernanceStatus


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
            project_id=str((package.requester_identity or {}).get("project_id") or "") or None,
            visibility_scope=dict(package.visibility_scope or {}),
            parent_package_ids=list(package.parent_package_ids),
            lineage_type=package.lineage_type,
            reuse_reason=package.reuse_reason,
            reused_count=self._existing_int(package.package_id, "reused_count"),
            last_reused_at=self._existing_str(package.package_id, "last_reused_at"),
            recommendation_count=self._existing_int(package.package_id, "recommendation_count"),
            last_recommended_at=self._existing_str(package.package_id, "last_recommended_at"),
            freshness_check_count=self._existing_int(package.package_id, "freshness_check_count"),
            used_in_decision_count=self._existing_int(package.package_id, "used_in_decision_count"),
            last_used_in_decision_at=self._existing_str(package.package_id, "last_used_in_decision_at"),
            governance=self._governance_for_package(package),
            lifecycle=dict(package.lifecycle or {}),
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

    def rebuild_from_package_store(self) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        package_root = self.path.parent
        if package_root.exists():
            for package_file in sorted(package_root.glob("EVPKG-*/package.json")):
                package = EvidencePackage(**json.loads(package_file.read_text(encoding="utf-8")))
                freshness = package.freshness or PackageFreshness()
                entries.append(EvidencePackageIndexEntry(
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
                    project_id=str((package.requester_identity or {}).get("project_id") or "") or None,
                    visibility_scope=dict(package.visibility_scope or {}),
                    parent_package_ids=list(package.parent_package_ids),
                    lineage_type=package.lineage_type,
                    reuse_reason=package.reuse_reason,
                    reused_count=self._existing_int(package.package_id, "reused_count"),
                    last_reused_at=self._existing_str(package.package_id, "last_reused_at"),
                    recommendation_count=self._existing_int(package.package_id, "recommendation_count"),
                    last_recommended_at=self._existing_str(package.package_id, "last_recommended_at"),
                    freshness_check_count=self._existing_int(package.package_id, "freshness_check_count"),
                    used_in_decision_count=self._existing_int(package.package_id, "used_in_decision_count"),
                    last_used_in_decision_at=self._existing_str(package.package_id, "last_used_in_decision_at"),
                    governance=self._governance_for_package(package),
                    lifecycle=dict(package.lifecycle or {}),
                ).model_dump())
        entries.sort(key=lambda item: item.get("created_at", ""))
        self._write({"schema_version": 1, "packages": entries})
        return {"schema_version": 1, "packages": entries, "package_count": len(entries)}

    def validate_index(self) -> dict[str, Any]:
        data = self._load()
        entries = list(data.get("packages", []))
        package_root = self.path.parent
        package_ids = {path.parent.name for path in package_root.glob("EVPKG-*/package.json")} if package_root.exists() else set()
        index_ids = {str(entry.get("package_id") or "") for entry in entries}
        missing_package_dirs = sorted(package_id for package_id in index_ids if package_id and package_id not in package_ids)
        missing_index_entries = sorted(package_id for package_id in package_ids if package_id not in index_ids)
        invalid_parent_refs: list[dict[str, str]] = []
        for entry in entries:
            child_id = str(entry.get("package_id") or "")
            for parent_id in list(entry.get("parent_package_ids") or []):
                if parent_id not in package_ids:
                    invalid_parent_refs.append({"package_id": child_id, "parent_package_id": parent_id})
        status = "pass" if not missing_package_dirs and not missing_index_entries and not invalid_parent_refs else "fail"
        return {
            "status": status,
            "package_count": len(package_ids),
            "index_entry_count": len(index_ids),
            "missing_package_dirs": missing_package_dirs,
            "missing_index_entries": missing_index_entries,
            "invalid_parent_refs": invalid_parent_refs,
        }

    def record_reuse(self, parent_package_ids: list[str]) -> None:
        self._increment_usage(parent_package_ids, "reused_count", "last_reused_at")

    def record_recommendation(self, package_ids: list[str]) -> None:
        self._increment_usage(package_ids, "recommendation_count", "last_recommended_at")

    def record_freshness_check(self, package_id: str) -> None:
        self._increment_usage([package_id], "freshness_check_count", "last_freshness_check_at")

    def record_decision_use(self, package_ids: list[str]) -> None:
        self._increment_usage(package_ids, "used_in_decision_count", "last_used_in_decision_at")

    def mark_deprecated(self, package_id: str, *, actor: str, reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self._load()
        entry = self._require_entry(data, package_id)
        old = dict(entry.get("governance") or {})
        governance = self._coerce_governance(old)
        now = datetime.now(timezone.utc).isoformat()
        governance.status = PackageGovernanceStatus.DEPRECATED
        governance.deprecated = True
        governance.deprecated_at = now
        governance.deprecated_by = actor
        governance.deprecation_reason = str(reason or "Package deprecated by governance action.")
        governance = self._score_governance(entry, governance)
        entry["governance"] = governance.model_dump()
        self._write(data)
        return old, dict(entry["governance"])

    def mark_superseded(self, package_id: str, *, superseded_by_package_id: str, reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self._load()
        entry = self._require_entry(data, package_id)
        if package_id == superseded_by_package_id:
            raise ValueError("package_cannot_supersede_itself")
        replacement = self._require_entry(data, superseded_by_package_id)
        if entry.get("project_id") and replacement.get("project_id") and entry.get("project_id") != replacement.get("project_id"):
            raise ValueError("supersession_project_mismatch")
        if str(replacement.get("created_at") or "") <= str(entry.get("created_at") or ""):
            raise ValueError("supersession_replacement_must_be_newer")
        old = dict(entry.get("governance") or {})
        governance = self._coerce_governance(old)
        governance.status = PackageGovernanceStatus.SUPERSEDED
        governance.superseded_by_package_id = superseded_by_package_id
        governance.superseded_at = datetime.now(timezone.utc).isoformat()
        governance.supersession_reason = str(reason or "Package superseded by newer governed evidence package.")
        governance = self._score_governance(entry, governance)
        entry["governance"] = governance.model_dump()
        self._write(data)
        return old, dict(entry["governance"])

    def _increment_usage(self, package_ids: list[str], count_key: str, timestamp_key: str) -> None:
        if not package_ids:
            return
        data = self._load()
        now = datetime.now(timezone.utc).isoformat()
        for entry in data.get("packages", []):
            if entry.get("package_id") in package_ids:
                entry[count_key] = int(entry.get(count_key) or 0) + 1
                entry[timestamp_key] = now
                entry["governance"] = self._score_governance(entry, self._coerce_governance(entry.get("governance") or {})).model_dump()
        self._write(data)

    def _require_entry(self, data: dict[str, Any], package_id: str) -> dict[str, Any]:
        for entry in data.get("packages", []):
            if entry.get("package_id") == package_id:
                return entry
        raise ValueError("evidence_package_index_entry_not_found")

    def _existing_int(self, package_id: str, key: str) -> int:
        for entry in self.list_entries():
            if entry.get("package_id") == package_id:
                return int(entry.get(key) or 0)
        return 0

    def _existing_str(self, package_id: str, key: str) -> str | None:
        for entry in self.list_entries():
            if entry.get("package_id") == package_id:
                return entry.get(key)
        return None

    def _governance_for_package(self, package: EvidencePackage) -> PackageGovernanceMetadata:
        existing = {}
        for entry in self.list_entries():
            if entry.get("package_id") == package.package_id:
                existing = dict(entry.get("governance") or {})
                break
        return self._score_governance({"stale": bool((package.freshness or PackageFreshness()).stale), "lineage_type": package.lineage_type.value, **existing}, self._coerce_governance(existing))

    def _coerce_governance(self, raw: dict[str, Any]) -> PackageGovernanceMetadata:
        if not raw:
            return PackageGovernanceMetadata()
        return PackageGovernanceMetadata(**raw)

    def _score_governance(self, entry: dict[str, Any], governance: PackageGovernanceMetadata) -> PackageGovernanceMetadata:
        score = 100
        reasons: list[str] = []
        reused = int(entry.get("reused_count") or 0)
        if reused >= 20:
            score += 20; reasons.append("high reuse count")
        elif reused >= 5:
            score += 10; reasons.append("moderate reuse count")
        if entry.get("stale"):
            score -= 20; governance.freshness_signal = "stale"; reasons.append("freshness drift detected")
        else:
            governance.freshness_signal = "fresh"
        if governance.deprecated or governance.status == PackageGovernanceStatus.DEPRECATED:
            score -= 40; governance.usage_signal = "deprecated"; reasons.append("package deprecated")
        elif reused >= 5:
            governance.usage_signal = "high_reuse"
        elif reused > 0:
            governance.usage_signal = "reused"
        else:
            governance.usage_signal = "neutral"
        if governance.superseded_by_package_id or governance.status == PackageGovernanceStatus.SUPERSEDED:
            score -= 60; governance.lineage_signal = "superseded"; reasons.append("package superseded")
        else:
            governance.lineage_signal = str(entry.get("lineage_type") or "original")
        if governance.status == PackageGovernanceStatus.RESTRICTED:
            score -= 100; reasons.append("package restricted")
        governance.governance_score = max(0, min(130, score))
        governance.governance_reason = "; ".join(reasons) if reasons else "Package is active and usable."
        return governance


    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "packages": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
