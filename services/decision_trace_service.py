from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.capability_audit_record import CapabilityAuditRecord
from models.decision_trace import DecisionTrace, DecisionTraceOutcome
from services.capability_audit_service import CapabilityAuditService
from services.evidence_package_freshness_service import EvidencePackageFreshnessService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.evidence_broker_service import EvidenceBrokerService


class DecisionTraceService:
    """Creates and discovers append-only Chair decision trace records."""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "decision_traces"
        self.index_path = self.root / "index.json"
        self.audit = CapabilityAuditService(self.repo_root)
        self.package_index = EvidencePackageIndexService(self.repo_root)

    def create_trace(
        self,
        *,
        decision_summary: str,
        outcome: str,
        requester_identity: dict[str, Any] | None = None,
        decision_id: str | None = None,
        decision_type: str = "governance",
        proposal_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        consultation_ids: list[str] | None = None,
        validation_ids: list[str] | None = None,
        repository_snapshot: dict[str, Any] | None = None,
        reason: str = "",
        outcome_metadata: dict[str, Any] | None = None,
        related_entities: dict[str, list[str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DecisionTrace:
        requester = requester_identity or {}
        package_ids = [str(item) for item in evidence_package_ids or [] if str(item)]
        for package_id in package_ids:
            self._assert_package_visible(package_id, requester)
        trace = DecisionTrace(
            decision_id=decision_id or None or f"DEC-{__import__('uuid').uuid4().hex[:12].upper()}",
            decision_type=str(decision_type or "governance"),
            decision_summary=str(decision_summary or ""),
            outcome=DecisionTraceOutcome(str(outcome or "").lower()),
            proposal_id=proposal_id,
            evidence_package_ids=package_ids,
            consultation_ids=[str(item) for item in consultation_ids or [] if str(item)],
            validation_ids=[str(item) for item in validation_ids or [] if str(item)],
            repository_snapshot=dict(repository_snapshot or {}),
            actor_identity=dict(requester),
            reason=str(reason or ""),
            outcome_metadata=dict(outcome_metadata or {}),
            related_entities={key: [str(item) for item in value] for key, value in dict(related_entities or {}).items()},
            metadata=dict(metadata or {}),
        )
        self._persist(trace)
        self.package_index.record_decision_use(package_ids)
        self._audit("decision.trace.create", requester, True, "decision_trace_created", {
            "trace_id": trace.trace_id,
            "decision_id": trace.decision_id,
            "outcome": trace.outcome.value,
            "proposal_id": trace.proposal_id,
            "evidence_package_ids": trace.evidence_package_ids,
        })
        return trace

    def get_trace(self, trace_id: str, *, requester_identity: dict[str, Any] | None = None, include_freshness: bool = True) -> dict[str, Any]:
        requester = requester_identity or {}
        trace = self._load_trace(trace_id)
        self._assert_trace_visible(trace, requester)
        result = trace.model_dump()
        result["evidence_packages"] = [self._package_summary(package_id, requester, include_freshness=include_freshness) for package_id in trace.evidence_package_ids]
        self._audit("decision.trace.get", requester, True, "decision_trace_returned", {"trace_id": trace.trace_id})
        return result

    def list_traces(
        self,
        *,
        requester_identity: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        decision_id: str | None = None,
        proposal_id: str | None = None,
        evidence_package_id: str | None = None,
        outcome: str | None = None,
        summary_contains: str | None = None,
    ) -> dict[str, Any]:
        requester = requester_identity or {}
        entries = [entry for entry in self._load_index().get("traces", []) if self._entry_visible(entry, requester)]
        entries = [entry for entry in entries if self._matches(entry, decision_id=decision_id, proposal_id=proposal_id, evidence_package_id=evidence_package_id, outcome=outcome, summary_contains=summary_contains)]
        entries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        effective_limit = self._limit(limit)
        effective_offset = max(0, int(offset or 0))
        page = entries[effective_offset:effective_offset + effective_limit]
        self._audit("decision.trace.list", requester, True, "decision_traces_listed", {"returned": len(page), "total": len(entries)})
        return {
            "traces": page,
            "pagination": {
                "limit": effective_limit,
                "offset": effective_offset,
                "total": len(entries),
                "returned": len(page),
                "has_more": effective_offset + effective_limit < len(entries),
                "next_offset": effective_offset + effective_limit if effective_offset + effective_limit < len(entries) else None,
            },
        }

    def history_for_package(self, package_id: str, *, requester_identity: dict[str, Any] | None = None) -> dict[str, Any]:
        requester = requester_identity or {}
        self._assert_package_visible(package_id, requester)
        result = self.list_traces(requester_identity=requester, evidence_package_id=package_id, limit=self.MAX_LIMIT)
        return {"package_id": package_id, "traces": result["traces"], "trace_count": result["pagination"]["total"]}

    def _persist(self, trace: DecisionTrace) -> None:
        path = self.root / trace.trace_id / "trace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("decision_trace_is_append_only")
        payload = trace.model_dump()
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        index = self._load_index()
        entries = [entry for entry in index.get("traces", []) if entry.get("trace_id") != trace.trace_id]
        entries.append(self._summary(trace))
        entries.sort(key=lambda item: item.get("created_at", ""))
        self._write_index({"schema_version": 1, "traces": entries})

    def _summary(self, trace: DecisionTrace) -> dict[str, Any]:
        project_id = str((trace.actor_identity or {}).get("project_id") or "") or None
        return {
            "trace_id": trace.trace_id,
            "decision_id": trace.decision_id,
            "decision_type": trace.decision_type,
            "decision_summary": trace.decision_summary,
            "outcome": trace.outcome.value,
            "proposal_id": trace.proposal_id,
            "evidence_package_ids": list(trace.evidence_package_ids),
            "consultation_ids": list(trace.consultation_ids),
            "validation_ids": list(trace.validation_ids),
            "repository_snapshot": dict(trace.repository_snapshot or {}),
            "project_id": project_id,
            "created_at": trace.created_at,
            "reason": trace.reason,
            "outcome_metadata": dict(trace.outcome_metadata or {}),
            "related_entities": dict(trace.related_entities or {}),
        }

    def _package_summary(self, package_id: str, requester: dict[str, Any], *, include_freshness: bool) -> dict[str, Any]:
        self._assert_package_visible(package_id, requester)
        entry = next((item for item in self.package_index.list_entries() if item.get("package_id") == package_id), {})
        result = {
            "package_id": package_id,
            "proposal_id": entry.get("proposal_id"),
            "evidence_plan_id": entry.get("evidence_plan_id"),
            "objective": entry.get("objective"),
            "created_at": entry.get("created_at"),
            "freshness_status": entry.get("freshness_status"),
            "stale": bool(entry.get("stale", False)),
            "governance": entry.get("governance") or {},
            "used_in_decision_count": int(entry.get("used_in_decision_count") or 0),
            "last_used_in_decision_at": entry.get("last_used_in_decision_at"),
        }
        if include_freshness:
            try:
                package = EvidenceBrokerService(self.repo_root).load_package(package_id, requester_identity=requester, evaluate_freshness=False)
                freshness = EvidencePackageFreshnessService(self.repo_root).evaluate(package)
                result["current_freshness"] = freshness.model_dump()
            except Exception as exc:
                result["current_freshness"] = {"status": "error", "stale": True, "freshness_reason": str(exc)}
        return result

    def _assert_trace_visible(self, trace: DecisionTrace, requester: dict[str, Any]) -> None:
        trace_project = str((trace.actor_identity or {}).get("project_id") or "")
        requester_project = str(requester.get("project_id") or "")
        if trace_project and requester_project and trace_project != requester_project:
            raise ValueError("decision_trace_project_scope_denied")
        for package_id in trace.evidence_package_ids:
            self._assert_package_visible(package_id, requester)

    def _entry_visible(self, entry: dict[str, Any], requester: dict[str, Any]) -> bool:
        trace_project = str(entry.get("project_id") or "")
        requester_project = str(requester.get("project_id") or "")
        if trace_project and requester_project and trace_project != requester_project:
            return False
        for package_id in list(entry.get("evidence_package_ids") or []):
            try:
                self._assert_package_visible(str(package_id), requester)
            except Exception:
                return False
        return True

    def _assert_package_visible(self, package_id: str, requester: dict[str, Any]) -> None:
        if str(requester.get("agent_id") or "").lower() == "chair":
            package = EvidenceBrokerService(self.repo_root).load_package(package_id, requester_identity=requester, evaluate_freshness=False)
            package_project = str((package.requester_identity or {}).get("project_id") or "")
            requester_project = str(requester.get("project_id") or "")
            if package_project and requester_project and package_project != requester_project:
                raise ValueError("evidence_package_project_scope_denied")
            return
        from services.evidence_package_lifecycle_service import EvidencePackageLifecycleService
        EvidencePackageLifecycleService(self.repo_root).rehydrate(package_id, requester_identity=requester)

    def _matches(self, entry: dict[str, Any], *, decision_id: str | None, proposal_id: str | None, evidence_package_id: str | None, outcome: str | None, summary_contains: str | None) -> bool:
        if decision_id and entry.get("decision_id") != decision_id:
            return False
        if proposal_id and entry.get("proposal_id") != proposal_id:
            return False
        if evidence_package_id and evidence_package_id not in list(entry.get("evidence_package_ids") or []):
            return False
        if outcome and str(entry.get("outcome") or "") != str(outcome).lower():
            return False
        if summary_contains and str(summary_contains).lower() not in str(entry.get("decision_summary") or "").lower():
            return False
        return True

    def _load_trace(self, trace_id: str) -> DecisionTrace:
        path = self.root / trace_id / "trace.json"
        if not path.exists():
            raise ValueError("decision_trace_not_found")
        return DecisionTrace(**json.loads(path.read_text(encoding="utf-8")))

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": 1, "traces": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

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
