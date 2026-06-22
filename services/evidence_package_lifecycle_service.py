from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.capability_audit_record import CapabilityAuditRecord
from models.evidence_package import EvidencePackage, PackageLineageType
from services.capability_audit_service import CapabilityAuditService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_freshness_service import EvidencePackageFreshnessService
from services.evidence_package_index_service import EvidencePackageIndexService


class EvidencePackageLifecycleService:
    """Discovery, reuse, lineage, and operational UX for immutable evidence packages."""

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
        entries = [entry for entry in self.index.list_entries() if self._eligible_entry(entry, requester, require_visibility=False)]
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

    def recommend(
        self,
        *,
        objective: str,
        requester_identity: dict[str, Any] | None = None,
        limit: int | None = None,
        min_similarity: float = 0.1,
    ) -> dict[str, Any]:
        requester = requester_identity or {}
        objective = str(objective or "").strip()
        if not objective:
            raise ValueError("objective_required")
        recommendations: list[dict[str, Any]] = []
        for entry in self.index.list_entries():
            if not self._eligible_entry(entry, requester, require_visibility=True):
                continue
            similarity = self._similarity(objective, self._entry_context(entry))
            if similarity < min_similarity:
                continue
            recommendations.append({
                "package_id": entry.get("package_id"),
                "objective": entry.get("objective"),
                "proposal_id": entry.get("proposal_id"),
                "evidence_plan_id": entry.get("evidence_plan_id"),
                "similarity": similarity,
                "freshness_status": entry.get("freshness_status", "unchanged"),
                "stale": bool(entry.get("stale", False)),
                "retrieval_confidence": entry.get("retrieval_confidence", 0.0),
                "primary_count": entry.get("primary_count", 0),
                "supporting_count": entry.get("supporting_count", 0),
                "validation_count": entry.get("validation_count", 0),
                "parent_package_ids": list(entry.get("parent_package_ids") or []),
                "reused_count": int(entry.get("reused_count") or 0),
                "recommendation_reason": self._recommendation_reason(similarity, entry),
            })
        recommendations.sort(key=lambda item: (item["stale"], -item["similarity"], -float(item.get("retrieval_confidence") or 0.0)))
        effective_limit = self._limit(limit)
        page = recommendations[:effective_limit]
        self._audit("evidence.package.recommend", requester, True, "evidence_package_recommendations_returned", {
            "objective": objective,
            "total_candidates": len(recommendations),
            "returned": len(page),
            "visibility_filtered": True,
            "advisory_only": True,
        })
        return {
            "objective": objective,
            "recommended_packages": page,
            "summary": {"total_candidates": len(recommendations), "returned": len(page), "advisory_only": True},
            "governance": {"chair_authority_required": True, "automatic_reuse": False, "visibility_filtered": True},
        }

    def reuse_package(
        self,
        package_id: str,
        *,
        requester_identity: dict[str, Any] | None = None,
        objective: str | None = None,
        lineage_type: str = "reuse",
        reuse_reason: str = "Chair approved evidence package reuse.",
        automatic_refresh: bool = False,
    ) -> EvidencePackage:
        if automatic_refresh:
            raise ValueError("automatic_refresh_not_allowed")
        requester = requester_identity or {}
        parent = self._load_authorized_package(package_id, requester, require_visibility=True)
        try:
            parsed_lineage = PackageLineageType(str(lineage_type or "reuse").lower())
        except ValueError:
            parsed_lineage = PackageLineageType.REUSE
        if parsed_lineage == PackageLineageType.NONE:
            parsed_lineage = PackageLineageType.REUSE
        child = parent.model_copy(deep=True)
        child.package_id = f"EVPKG-{uuid4().hex[:12].upper()}"
        child.objective = str(objective or parent.objective)
        child.created_at = datetime.now(timezone.utc).isoformat()
        child.parent_package_ids = [parent.package_id]
        child.lineage_type = parsed_lineage
        child.reuse_reason = str(reuse_reason or "Chair approved evidence package reuse.")
        child.freshness = None
        child.requester_identity = dict(requester)
        child.visibility_scope = self._visibility_scope(requester)
        child.audit_metadata = {
            **dict(parent.audit_metadata or {}),
            "reused_from_package_id": parent.package_id,
            "parent_package_ids": [parent.package_id],
            "lineage_type": parsed_lineage.value,
            "reuse_reason": child.reuse_reason,
            "reuse_created_at": child.created_at,
            "requester_identity": dict(requester),
            "immutable_reuse_child": True,
        }
        self._persist(child)
        self.index.record_reuse([parent.package_id])
        self._audit("evidence.package.reuse", requester, True, "evidence_package_reuse_child_created", {
            "parent_package_id": parent.package_id,
            "child_package_id": child.package_id,
            "lineage_type": parsed_lineage.value,
            "reuse_reason": child.reuse_reason,
            "automatic_refresh": False,
        })
        return child

    def lineage(self, package_id: str, *, requester_identity: dict[str, Any] | None = None) -> dict[str, Any]:
        requester = requester_identity or {}
        package = self._load_authorized_package(package_id, requester, require_visibility=True)
        entries = [entry for entry in self.index.list_entries() if self._eligible_entry(entry, requester, require_visibility=True)]
        by_id = {str(entry.get("package_id")): entry for entry in entries}
        parents = [by_id[parent_id] for parent_id in package.parent_package_ids if parent_id in by_id]
        children = [entry for entry in entries if package.package_id in list(entry.get("parent_package_ids") or [])]
        ancestors = self._walk_ancestors(package.package_id, by_id)
        descendants = self._walk_descendants(package.package_id, by_id)
        result = {
            "package_id": package.package_id,
            "lineage_type": package.lineage_type.value,
            "reuse_reason": package.reuse_reason,
            "parent_package_ids": list(package.parent_package_ids),
            "parents": parents,
            "children": children,
            "ancestors": ancestors,
            "descendants": descendants,
        }
        self._audit("evidence.package.lineage", requester, True, "evidence_package_lineage_returned", {"package_id": package.package_id})
        return result

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
            "visibility_scope": package.visibility_scope,
            "parent_package_ids": list(package.parent_package_ids),
            "lineage_type": package.lineage_type.value,
            "reuse_reason": package.reuse_reason,
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
        package = self._load_authorized_package(package_id, requester, require_visibility=True)
        self._audit("evidence.package.rehydrate", requester, True, "evidence_package_rehydrated", {"package_id": package.package_id})
        return package

    def evaluate_freshness(self, package_id: str, *, requester_identity: dict[str, Any] | None = None) -> dict[str, Any]:
        requester = requester_identity or {}
        package = self._load_authorized_package(package_id, requester, require_visibility=True)
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

    def _load_authorized_package(self, package_id: str, requester: dict[str, Any], *, require_visibility: bool = False) -> EvidencePackage:
        package = EvidenceBrokerService(self.repo_root).load_package(package_id, requester_identity=requester, evaluate_freshness=False)
        if not self._package_same_project(package, requester):
            self._audit("evidence.package.access", requester, False, "evidence_package_project_scope_denied", {"package_id": package_id})
            raise ValueError("evidence_package_project_scope_denied")
        if require_visibility and not self._package_visible_to_requester(package, requester):
            self._audit("evidence.package.access", requester, False, "evidence_package_visibility_denied", {"package_id": package_id})
            raise ValueError("evidence_package_visibility_denied")
        return package

    def _package_same_project(self, package: EvidencePackage, requester: dict[str, Any]) -> bool:
        requested_project = str(requester.get("project_id") or "")
        package_project = str((package.requester_identity or {}).get("project_id") or "")
        if package_project and requested_project and package_project != requested_project:
            return False
        return True

    def _package_visible_to_requester(self, package: EvidencePackage, requester: dict[str, Any]) -> bool:
        scope = package.visibility_scope or self._visibility_scope(package.requester_identity or {})
        return self._scope_visible(scope, requester)

    def _same_project(self, entry: dict[str, Any], requester: dict[str, Any]) -> bool:
        package_project = str(entry.get("project_id") or "")
        requested_project = str(requester.get("project_id") or "")
        if package_project and requested_project and package_project != requested_project:
            return False
        if package_project:
            return True
        package_id = str(entry.get("package_id") or "")
        if not package_id:
            return False
        try:
            package = self._load_package_unchecked(package_id)
        except Exception:
            return False
        return self._package_same_project(package, requester)

    def _eligible_entry(self, entry: dict[str, Any], requester: dict[str, Any], *, require_visibility: bool) -> bool:
        if not self._same_project(entry, requester):
            return False
        if not require_visibility:
            return True
        scope = dict(entry.get("visibility_scope") or {})
        if not scope:
            try:
                scope = self._load_package_unchecked(str(entry.get("package_id") or "")).visibility_scope
            except Exception:
                scope = {}
        return self._scope_visible(scope, requester)

    def _scope_visible(self, scope: dict[str, Any], requester: dict[str, Any]) -> bool:
        for key in ("project_id", "agent_id", "client_id", "participant_id"):
            scoped = scope.get(key)
            requested = requester.get(key)
            if scoped and requested and str(scoped) != str(requested):
                return False
            if scoped and key == "agent_id" and not requested:
                return False
        return True

    def _visibility_scope(self, requester: dict[str, Any]) -> dict[str, Any]:
        return {
            key: str(requester.get(key))
            for key in ("project_id", "agent_id", "client_id", "participant_id")
            if requester.get(key)
        }

    def _persist(self, package: EvidencePackage) -> None:
        path = self.package_root / package.package_id / "package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(package.model_dump(), indent=2, sort_keys=True), encoding="utf-8")
        self.index.upsert_package(package)

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
        if context_contains and context_contains.lower() not in self._entry_context(entry).lower():
            return False
        created_at = str(entry.get("created_at") or "")
        if created_before and created_at and created_at >= created_before:
            return False
        if created_after and created_at and created_at <= created_after:
            return False
        return True

    def _entry_context(self, entry: dict[str, Any]) -> str:
        return " ".join(str(entry.get(key) or "") for key in (
            "objective", "package_id", "proposal_id", "evidence_plan_id", "freshness_status", "lineage_type", "reuse_reason"
        ))

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
        return {"total_count": len(entries), "stale_count": stale_count, "fresh_count": len(entries) - stale_count}

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
        return {"retrieval_methods": methods, "hinted_count": hinted, "unhinted_count": len(package.all_evidence()) - hinted, "matched_terms": sorted(matched_terms)}

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

    def _walk_ancestors(self, package_id: str, by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        def visit(current_id: str) -> None:
            for parent_id in list(by_id.get(current_id, {}).get("parent_package_ids") or []):
                if parent_id in seen or parent_id not in by_id:
                    continue
                seen.add(parent_id)
                result.append(by_id[parent_id])
                visit(parent_id)
        visit(package_id)
        return result

    def _walk_descendants(self, package_id: str, by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        def visit(current_id: str) -> None:
            for entry_id, entry in by_id.items():
                if entry_id in seen or current_id not in list(entry.get("parent_package_ids") or []):
                    continue
                seen.add(entry_id)
                result.append(entry)
                visit(entry_id)
        visit(package_id)
        return result

    def _similarity(self, left: str, right: str) -> float:
        left_terms = self._terms(left)
        right_terms = self._terms(right)
        if not left_terms or not right_terms:
            return 0.0
        overlap = len(left_terms.intersection(right_terms))
        union = len(left_terms.union(right_terms))
        contains_bonus = 0.2 if left.lower() in right.lower() or right.lower() in left.lower() else 0.0
        return round(min(1.0, (overlap / union) + contains_bonus), 3)

    def _terms(self, text: str) -> set[str]:
        stop = {"need", "understand", "current", "existing", "with", "that", "this", "from", "before", "intent", "evidence", "request", "package"}
        return {word.replace(".", "_").replace("-", "_") for word in re.findall(r"[a-zA-Z_][a-zA-Z0-9_\.\-]*", text.lower()) if len(word) >= 4 and word not in stop}

    def _recommendation_reason(self, similarity: float, entry: dict[str, Any]) -> str:
        freshness = entry.get("freshness_status", "unchanged")
        if entry.get("stale"):
            return f"Objective similarity {similarity:.2f}; package is stale ({freshness}) and requires Chair review before reuse."
        return f"Objective similarity {similarity:.2f}; package freshness is {freshness}."

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
