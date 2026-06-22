from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.capability_audit_record import CapabilityAuditRecord
from models.evidence_package import EvidencePackage, EvidencePackageIndexEntry
from services.capability_audit_service import CapabilityAuditService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_freshness_service import EvidencePackageFreshnessService
from services.evidence_package_index_service import EvidencePackageIndexService


class EvidencePackageLifecycleService:
    """Discovery and operational UX for immutable evidence packages.

    Package contents are never modified by this service. Freshness checks update
    only the package index as the last-known package lifecycle state.
    """

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.package_root = self.repo_root / ".ageix" / "evidence_packages"
        self.index = EvidencePackageIndexService(self.repo_root)
        self.freshness = EvidencePackageFreshnessService(self.repo_root)
        self.audit = CapabilityAuditService(self.repo_root)

    def list_packages(
        self,
        *,
        requester_identity: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        proposal_id: str | None = None,
        evidence_plan_id: str | None = None,
        stale: bool | None = None,
        objective_contains: str | None = None,
        context_contains: str | None = None,
        created_before: str | None = None,
        created_after: str | None = None,
    ) -> dict[str, Any]:
        requester = requester_identity or {}
        effective_limit = self._limit(limit)
        effective_offset = max(0, int(offset or 0))
        entries = [entry for entry in self.index.list_entries() if self._same_project(entry, requester)]
        entries = [
            entry for entry in entries
            if self._matches(
                entry,
                proposal_id=proposal_id,
                evidence_plan_id=evidence_plan_id,
                stale=stale,
                objective_contains=objective_contains,
                context_contains=context_contains,
                created_before=created_before,
                created_after=created_after,
            )
        ]
        entries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        page = entries[effective_offset:effective_offset + effective_limit]
        self._audit("evidence.package.list", requester, True, "evidence_package_listed", {
            "limit": effective_limit,
            "offset": effective_offset,
            "total": len(entries),
            "returned": len(page),
            "filters": {
                "proposal_id": proposal_id,
                "evidence_plan_id": evidence_plan_id,
                "stale": stale,
                "objective_contains": objective_contains,
                "context_contains": context_contains,
                "created_before": created_before,
                "created_after": created_after,
            },
        })
        return {
            "packages": page,
            "pagination": {
                "limit": effective_limit,
                "offset": effective_offset,
                "total": len(entries),
                "returned": len(page),
                "has_more": effective_offset + effective_limit < len(entries),
                "next_offset": effective_offset + effective_limit if effective_offset + effective_limit < len(entries) else None,
            },
            "summary": self._summary(entries),
        }

    def details(self, package_id: str, *, requester_identity: dict[str, Any] | None = None) -> dict[str, Any]:
        requester = requester_identity or {}
        package = self._load_authorized_package(package_id, requester)
        result = {
            "package_id": package.package_id,
            "proposal_id": package.proposal_id,
            "evidence_plan_id": package.evidence_plan_id,
            "objective": package.objective,
            "intent": package.intent,
            "created_at": package.created_at,
            "repository_snapshot": package.repository_snapshot,
            "retrieval_confidence": package.retrieval_confidence,
            "confidence_reason": package.confidence_reason,
            "coverage_gaps": list(package.coverage_gaps),
            "recommended_followup_requests": list(package.recommended_followup_requests),
            "freshness": package.freshness.model_dump() if package.freshness else self._indexed_freshness(package.package_id),
            "evidence_counts": self._package_counts(package),
            "provenance_summary": self._provenance_summary(package),
            "evidence_manifest": [self._manifest_item(item) for item in package.all_evidence()],
            "requester_identity": package.requester_identity,
            "audit_metadata": package.audit_metadata,
        }
        self._audit("evidence.package.details", requester, True, "evidence_package_details_returned", {"package_id": package.package_id})
        return result

    def rehydrate(self, package_id: str, *, requester_identity: dict[str, Any] | None = None) -> EvidencePackage:
        requester = requester_identity or {}
        package = self._load_authorized_package(package_id, requester)
        self._audit("evidence.package.rehydrate", requester, True, "evidence_package_rehydrated", {"package_id": package.package_id})
        return package

    def evaluate_freshness(self, package_id: str, *, requester_identity: dict[str, Any] | None = None) -> dict[str, Any]:
        requester = requester_identity or {}
        package = self._load_authorized_package(package_id, requester)
        freshness = self.freshness.evaluate(package)
        result = {
            "package_id": package.package_id,
            "proposal_id": package.proposal_id,
            "evidence_plan_id": package.evidence_plan_id,
            "freshness": freshness.model_dump(),
            "freshness_status": freshness.status.value,
            "stale": freshness.stale,
            "changed_paths": list(freshness.changed_paths),
            "missing_paths": list(freshness.missing_paths),
            "unchanged_paths": list(freshness.unchanged_paths),
        }
        self._audit("evidence.package.freshness", requester, True, "evidence_package_freshness_evaluated", result)
        return result

    def _load_authorized_package(self, package_id: str, requester: dict[str, Any]) -> EvidencePackage:
        package = EvidenceBrokerService(self.repo_root).load_package(package_id, requester_identity=requester, evaluate_freshness=False)
        if not self._package_same_project(package, requester):
            self._audit("evidence.package.access", requester, False, "evidence_package_project_scope_denied", {"package_id": package_id})
            raise ValueError("evidence_package_project_scope_denied")
        return package

    def _package_same_project(self, package: EvidencePackage, requester: dict[str, Any]) -> bool:
        requested_project = str(requester.get("project_id") or "")
        package_project = str((package.requester_identity or {}).get("project_id") or "")
        if package_project and requested_project and package_project != requested_project:
            return False
        return True

    def _same_project(self, entry: dict[str, Any], requester: dict[str, Any]) -> bool:
        package_project = str(entry.get("project_id") or "")
        requested_project = str(requester.get("project_id") or "")
        if package_project and requested_project and package_project != requested_project:
            return False
        if package_project:
            return True
        # Pre-17.3 index rows may not include project_id. Load only when needed so
        # old package indexes remain discoverable without migration.
        package_id = str(entry.get("package_id") or "")
        if not package_id:
            return False
        try:
            package = self._load_package_unchecked(package_id)
        except Exception:
            return False
        return self._package_same_project(package, requester)

    def _load_package_unchecked(self, package_id: str) -> EvidencePackage:
        path = self.package_root / package_id / "package.json"
        if not path.exists():
            raise ValueError("evidence_package_not_found")
        return EvidencePackage(**json.loads(path.read_text(encoding="utf-8")))

    def _matches(
        self,
        entry: dict[str, Any],
        *,
        proposal_id: str | None,
        evidence_plan_id: str | None,
        stale: bool | None,
        objective_contains: str | None,
        context_contains: str | None,
        created_before: str | None,
        created_after: str | None,
    ) -> bool:
        if proposal_id and entry.get("proposal_id") != proposal_id:
            return False
        if evidence_plan_id and entry.get("evidence_plan_id") != evidence_plan_id:
            return False
        if stale is not None and bool(entry.get("stale", False)) is not bool(stale):
            return False
        if objective_contains and objective_contains.lower() not in str(entry.get("objective") or "").lower():
            return False
        if context_contains:
            haystack = " ".join(str(entry.get(key) or "") for key in ("objective", "package_id", "proposal_id", "evidence_plan_id"))
            if context_contains.lower() not in haystack.lower():
                return False
        created_at = str(entry.get("created_at") or "")
        if created_before and created_at and created_at >= created_before:
            return False
        if created_after and created_at and created_at <= created_after:
            return False
        return True

    def _indexed_freshness(self, package_id: str) -> dict[str, Any] | None:
        for entry in self.index.list_entries():
            if entry.get("package_id") == package_id:
                return {
                    "status": entry.get("freshness_status"),
                    "stale": entry.get("stale", False),
                    "last_freshness_check_at": entry.get("last_freshness_check_at"),
                    "source": "index_last_known_state",
                }
        return None

    def _summary(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        stale_count = sum(1 for entry in entries if entry.get("stale"))
        return {
            "total_count": len(entries),
            "stale_count": stale_count,
            "fresh_count": len(entries) - stale_count,
        }

    def _package_counts(self, package: EvidencePackage) -> dict[str, int]:
        return {
            "primary_count": len(package.primary_evidence),
            "supporting_count": len(package.supporting_evidence),
            "validation_count": len(package.validation_evidence),
            "coverage_gap_count": len(package.coverage_gaps),
            "total_evidence_count": len(package.all_evidence()),
        }

    def _provenance_summary(self, package: EvidencePackage) -> dict[str, Any]:
        methods: dict[str, int] = {}
        hinted = 0
        matched_terms: set[str] = set()
        for item in package.all_evidence():
            provenance = item.provenance
            methods[provenance.retrieval_method] = methods.get(provenance.retrieval_method, 0) + 1
            if provenance.hinted:
                hinted += 1
            matched_terms.update(provenance.matched_terms)
        return {
            "retrieval_methods": methods,
            "hinted_count": hinted,
            "unhinted_count": len(package.all_evidence()) - hinted,
            "matched_terms": sorted(matched_terms),
        }

    def _manifest_item(self, item: Any) -> dict[str, Any]:
        return {
            "path": item.path,
            "classification": item.classification,
            "relevance_reason": item.relevance_reason,
            "retrieval_reason": item.retrieval_reason,
            "hinted": item.hinted,
            "content_hash": item.content_hash,
            "line_count": item.line_count,
            "returned_line_count": item.returned_line_count,
            "excerpted": item.excerpted,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "provenance": item.provenance.model_dump(),
        }

    def _limit(self, limit: int | None) -> int:
        if limit is None:
            return self.DEFAULT_LIMIT
        return max(1, min(self.MAX_LIMIT, int(limit)))

    def _audit(self, capability_id: str, requester: dict[str, Any], success: bool, reason: str, metadata: dict[str, Any] | None = None) -> None:
        self.audit.record(CapabilityAuditRecord(
            session_id=str(requester.get("session_id") or ""),
            agent_id=str(requester.get("agent_id") or ""),
            capability_id=capability_id,
            success=success,
            reason=reason,
            client_id=str(requester.get("client_id")) if requester.get("client_id") else None,
            project_id=str(requester.get("project_id")) if requester.get("project_id") else None,
            participant_id=str(requester.get("participant_id")) if requester.get("participant_id") else None,
            metadata=metadata or {},
        ))
