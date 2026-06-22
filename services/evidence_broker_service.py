from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.capability_audit_record import CapabilityAuditRecord
from models.evidence_access_proposal import EvidenceAccessDecision, EvidencePlan
from models.evidence_package import EvidencePackage, EvidencePackageItem, EvidenceProvenance
from services.capability_audit_service import CapabilityAuditService
from services.evidence_broker_planner_service import EvidenceBrokerPlannerService
from services.evidence_package_freshness_service import EvidencePackageFreshnessService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.evidence_retrieval_guard_service import EvidenceRetrievalGuardService


class EvidenceBrokerService:
    """Governed intent-satisfaction broker for approved evidence plans.

    The broker fulfills approved intent. Plan targets are advisory hints: they
    guide retrieval but neither whitelist nor cap the broker's search path.
    """

    TEXT_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".md", ".txt", ".toml", ".ini", ".cfg"}
    GENERATED_SUFFIXES = {".patch", ".diff", ".zip", ".tar", ".gz", ".tgz", ".pyc", ".pyo"}
    GENERATED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    DEFAULT_EXCERPT_LINES = 220
    FULL_FILE_RELEVANT_LINES = 1000

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.proposal_root = self.repo_root / ".ageix" / "manifests" / "evidence_access_proposals"
        self.package_root = self.repo_root / ".ageix" / "evidence_packages"
        self.planner = EvidenceBrokerPlannerService(self.repo_root)
        self.audit = CapabilityAuditService(self.repo_root)
        self.guard = EvidenceRetrievalGuardService(self.repo_root)
        self.index = EvidencePackageIndexService(self.repo_root)

    def request_evidence(
        self,
        *,
        proposal_id: str | None = None,
        evidence_plan_id: str | None = None,
        package_id: str | None = None,
        requester_identity: dict[str, Any] | None = None,
        evaluate_freshness: bool = True,
    ) -> EvidencePackage:
        requester = requester_identity or {}
        if package_id:
            return self.load_package(package_id, requester_identity=requester, evaluate_freshness=evaluate_freshness)
        proposal_payload, decision, plan = self._resolve_approved_plan(proposal_id=proposal_id, evidence_plan_id=evidence_plan_id)
        candidates = self._candidate_paths(plan, requester_identity=requester)
        items = [self._build_item(path, plan, hinted=(path in self._hinted_paths(plan))) for path in candidates]
        package = self._assemble_package(plan=plan, decision=decision, items=items, requester_identity=requester)
        package.audit_metadata.update({
            "proposal_id": decision.proposal_id,
            "evidence_plan_id": plan.plan_id,
            "intent": plan.objective,
            "evidence_retrieved": [item.path for item in items],
            "requester_identity": requester,
            "source_proposal_created_at": proposal_payload.get("created_at"),
        })
        self._persist(package)
        self.audit.record(CapabilityAuditRecord(
            session_id=str(requester.get("session_id") or ""),
            agent_id=str(requester.get("agent_id") or ""),
            capability_id="evidence.request",
            success=True,
            reason="evidence_package_retrieved",
            client_id=str(requester.get("client_id")) if requester.get("client_id") else None,
            project_id=str(requester.get("project_id")) if requester.get("project_id") else None,
            participant_id=str(requester.get("participant_id")) if requester.get("participant_id") else None,
            metadata={
                "intent": plan.objective,
                "evidence_plan_id": plan.plan_id,
                "evidence_retrieved": [item.path for item in items],
                "retrieval_confidence": package.retrieval_confidence,
                "confidence_reason": package.confidence_reason,
                "coverage_gaps": package.coverage_gaps,
                "package_id": package.package_id,
            },
        ))
        return package

    def load_package(self, package_id: str, *, requester_identity: dict[str, Any] | None = None, evaluate_freshness: bool = True) -> EvidencePackage:
        requester = requester_identity or {}
        path = self.package_root / package_id / "package.json"
        if not path.exists():
            raise ValueError("evidence_package_not_found")
        package = EvidencePackage(**json.loads(path.read_text(encoding="utf-8")))
        if evaluate_freshness:
            package.freshness = EvidencePackageFreshnessService(self.repo_root).evaluate(package)
        self.audit.record(CapabilityAuditRecord(
            session_id=str(requester.get("session_id") or ""),
            agent_id=str(requester.get("agent_id") or ""),
            capability_id="evidence.request",
            success=True,
            reason="evidence_package_rehydrated",
            client_id=str(requester.get("client_id")) if requester.get("client_id") else None,
            project_id=str(requester.get("project_id")) if requester.get("project_id") else None,
            participant_id=str(requester.get("participant_id")) if requester.get("participant_id") else None,
            metadata={
                "package_id": package.package_id,
                "proposal_id": package.proposal_id,
                "evidence_plan_id": package.evidence_plan_id,
                "freshness": package.freshness.model_dump() if package.freshness else None,
            },
        ))
        return package

    def _resolve_approved_plan(self, *, proposal_id: str | None, evidence_plan_id: str | None) -> tuple[dict[str, Any], EvidenceAccessDecision, EvidencePlan]:
        payload = self._load_payload(proposal_id=proposal_id, evidence_plan_id=evidence_plan_id)
        decision = EvidenceAccessDecision(**payload["decision"])
        plan = decision.evidence_plan
        if plan is None:
            raise ValueError("approved_evidence_plan_required")
        if decision.decision != "approved":
            raise ValueError("evidence_plan_not_approved")
        if evidence_plan_id and plan.plan_id != evidence_plan_id:
            raise ValueError("evidence_plan_id_mismatch")
        self._validate_not_expired(plan)
        return payload, decision, plan

    def _load_payload(self, *, proposal_id: str | None, evidence_plan_id: str | None) -> dict[str, Any]:
        if proposal_id:
            path = self.proposal_root / proposal_id / "proposal.json"
            if not path.exists():
                raise ValueError("evidence_proposal_not_found")
            return json.loads(path.read_text(encoding="utf-8"))
        if not evidence_plan_id:
            raise ValueError("proposal_id_or_evidence_plan_id_required")
        for path in sorted(self.proposal_root.glob("*/proposal.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            plan = payload.get("decision", {}).get("evidence_plan") or {}
            if plan.get("plan_id") == evidence_plan_id:
                return payload
        raise ValueError("evidence_plan_not_found")

    def _validate_not_expired(self, plan: EvidencePlan) -> None:
        if not plan.expires_at:
            raise ValueError("evidence_plan_expiration_required")
        expires_at = datetime.fromisoformat(str(plan.expires_at))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("evidence_plan_expired")

    def _candidate_paths(self, plan: EvidencePlan, requester_identity: dict[str, Any] | None = None) -> list[str]:
        hinted = list(self._hinted_paths(plan))
        text = " ".join([plan.objective, plan.reason, plan.target, plan.desired_outcome, " ".join(plan.evidence_needed)])
        discovered = self.planner._candidate_paths(plan.target, text)  # deterministic 17.0 planner seam; hints are advisory only.
        ordered: list[str] = []
        for path in [*hinted, *discovered]:
            if path not in ordered and self._retrievable(path, requester_identity=requester_identity):
                ordered.append(path)
        # Keep the MVP focused on intent satisfaction. This is not a file-count
        # budget; it prevents deterministic keyword matches from drifting into
        # repo-wide retrieval until architecture/dependency expansion exists.
        return ordered[:18]

    def _hinted_paths(self, plan: EvidencePlan) -> set[str]:
        return {target.target for target in plan.resolved_targets if target.target}

    def _retrievable(self, path: str, requester_identity: dict[str, Any] | None = None) -> bool:
        return self.guard.is_retrievable(path, requester_identity=requester_identity)

    def _build_item(self, path: str, plan: EvidencePlan, hinted: bool) -> EvidencePackageItem:
        full = self.repo_root / path
        content = full.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        classification = self._classification(path)
        strong_relevance = self._strong_relevance(path, plan)
        excerpted = len(lines) > self.DEFAULT_EXCERPT_LINES and not (strong_relevance and len(lines) <= self.FULL_FILE_RELEVANT_LINES)
        returned_lines = lines if not excerpted else lines[:self.DEFAULT_EXCERPT_LINES]
        returned_content = "\n".join(returned_lines) + ("\n" if returned_lines else "")
        matched_terms = sorted(term for term in self._terms(" ".join([plan.objective, plan.reason, plan.target, plan.desired_outcome])) if term in path.lower().replace("-", "_"))
        selection_reason = (
            "Path was an advisory evidence-plan hint and survived broker validation."
            if hinted else
            "Broker retrieved this unhinted path because it matched the approved intent."
        )
        classification_reason = self._classification_reason(path, classification)
        return EvidencePackageItem(
            path=path,
            classification=classification,
            relevance_reason=self._relevance_reason(path, classification, hinted),
            retrieval_reason=selection_reason,
            hinted=hinted,
            content=returned_content,
            content_hash=EvidencePackageFreshnessService.hash_content(content),
            line_count=len(lines),
            returned_line_count=len(returned_lines),
            excerpted=excerpted,
            start_line=1 if returned_lines else None,
            end_line=len(returned_lines) if returned_lines else None,
            provenance=EvidenceProvenance(
                retrieval_method="intent_plan_hint" if hinted else "intent_keyword_discovery",
                retrieval_source="evidence_broker",
                hinted=hinted,
                matched_terms=matched_terms,
                selection_reason=selection_reason,
                classification_reason=classification_reason,
            ),
            metadata={
                "full_file_returned": not excerpted,
                "strong_relevance": strong_relevance,
                "retrieval_method": "intent_plan_hint" if hinted else "intent_keyword_discovery",
                "hinted": hinted,
                "matched_terms": matched_terms,
                "selection_reason": selection_reason,
                "classification_reason": classification_reason,
            },
        )

    def _classification(self, path: str) -> str:
        lower = path.lower()
        if lower.startswith("tests/") or lower.startswith("scripts/smoke/") or "test_" in Path(lower).name:
            return "validation"
        if lower.startswith("models/") or "registry" in lower or lower.endswith((".json", ".yaml", ".yml")):
            return "supporting"
        if lower.startswith("services/") or lower.startswith("web/routes/") or lower.startswith("ageix_mcp/"):
            return "primary"
        return "supporting"

    def _classification_reason(self, path: str, classification: str) -> str:
        if classification == "validation":
            return "Path is test or smoke evidence based on its directory or filename."
        if classification == "primary":
            return "Path is implementation or interface evidence based on its service, route, or MCP directory."
        return "Path is supporting model, registry, schema, or configuration evidence."

    def _strong_relevance(self, path: str, plan: EvidencePlan) -> bool:
        terms = self._terms(" ".join([plan.objective, plan.reason, plan.target, plan.desired_outcome]))
        lower = path.lower().replace("-", "_")
        hits = sum(1 for term in terms if term in lower)
        return hits >= 2 or any(target.target == path and target.confidence >= 0.90 for target in plan.resolved_targets)

    def _terms(self, text: str) -> set[str]:
        stop = {"need", "understand", "current", "existing", "with", "that", "this", "from", "before", "intent", "evidence", "request"}
        return {word.replace(".", "_").replace("-", "_") for word in re.findall(r"[a-zA-Z_][a-zA-Z0-9_\.\-]*", text.lower()) if len(word) >= 4 and word not in stop}

    def _relevance_reason(self, path: str, classification: str, hinted: bool) -> str:
        hint = "hinted " if hinted else "unhinted "
        if classification == "primary":
            return f"{hint}implementation or interface evidence relevant to the approved intent."
        if classification == "validation":
            return f"{hint}test or smoke evidence that can validate the approved intent."
        return f"{hint}supporting model, registry, schema, or configuration evidence relevant to the approved intent."

    def _assemble_package(self, *, plan: EvidencePlan, decision: EvidenceAccessDecision, items: list[EvidencePackageItem], requester_identity: dict[str, Any]) -> EvidencePackage:
        primary = [item for item in items if item.classification == "primary"]
        supporting = [item for item in items if item.classification == "supporting"]
        validation = [item for item in items if item.classification == "validation"]
        confidence, reason, gaps, followups = self._score(primary, supporting, validation, items)
        return EvidencePackage(
            proposal_id=decision.proposal_id,
            evidence_plan_id=plan.plan_id,
            objective=plan.objective,
            intent=plan.intent_type,
            repository_snapshot=self._repository_snapshot(),
            primary_evidence=primary,
            supporting_evidence=supporting,
            validation_evidence=validation,
            retrieval_confidence=confidence,
            confidence_reason=reason,
            coverage_gaps=gaps,
            recommended_followup_requests=followups,
            requester_identity=requester_identity,
            visibility_scope=self._visibility_scope(requester_identity),
        )

    def _score(self, primary: list[EvidencePackageItem], supporting: list[EvidencePackageItem], validation: list[EvidencePackageItem], items: list[EvidencePackageItem]) -> tuple[float, str, list[str], list[str]]:
        gaps: list[str] = []
        followups: list[str] = []
        score = 0.15
        if primary:
            score += 0.42
        else:
            gaps.append("No primary implementation/interface evidence was retrieved.")
            followups.append("Request a narrower approved intent target that names the implementation service or route.")
        if supporting:
            score += 0.18
        else:
            gaps.append("No supporting model, registry, schema, or configuration evidence was retrieved.")
        if validation:
            score += 0.20
        else:
            gaps.append("No validation test or smoke evidence was retrieved.")
            followups.append("Request validation evidence for the approved intent if implementation confidence is not sufficient.")
        if any(not item.hinted for item in items):
            score += 0.05
        score = round(min(0.95, score), 3)
        if score >= 0.80:
            reason = "High retrieval confidence: package contains primary, supporting, and validation evidence for the approved intent."
        elif score >= 0.60:
            reason = "Moderate retrieval confidence: package contains primary evidence but has coverage gaps."
        else:
            reason = "Low retrieval confidence: retrieved evidence does not sufficiently cover the approved intent."
        return score, reason, gaps, followups

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

    def _repository_snapshot(self) -> dict[str, Any]:
        return {
            "git_commit": self._git_commit(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
            return result.stdout.strip() or None
        except Exception:
            return None
