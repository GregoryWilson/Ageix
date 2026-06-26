from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from models.evidence_access_proposal import EvidenceAccessProposal, EvidencePlan, EvidencePlanTarget
from services.repository_inventory_service import RepositoryInventoryService


class EvidenceBrokerPlannerService:
    """Plan intent-based evidence packages without retrieving source contents.

    Sprint 17.0 deliberately keeps this deterministic/rule-based with a clean seam
    for a future local LLM planner. The planner advises Chair; it never authorizes
    repository access by itself.
    """

    REPO_WALK_TERMS = {
        "entire repo",
        "entire repository",
        "whole repo",
        "whole repository",
        "all files",
        "all source",
        "everything",
        "full source",
        "source dump",
        "repo dump",
        "repository dump",
        "entire codebase",
        "whole codebase",
    }

    GENERATED_PATH_SUFFIXES = {
        ".patch",
        ".diff",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".pyc",
        ".pyo",
    }
    GENERATED_PATH_PARTS = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".git",
        ".venv",
        "venv",
    }

    FEATURE_TERMS = {"design", "add", "build", "implement", "feature", "support", "adapter", "expose"}
    DEBUG_TERMS = {"bug", "debug", "failing", "failure", "fix", "investigate", "error", "unknown"}
    ARCH_TERMS = {"architecture", "architectural", "pattern", "component", "domain", "design"}
    VALIDATION_TERMS = {"test", "validate", "smoke", "regression", "verification"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.inventory = RepositoryInventoryService(self.repo_root)

    def plan(self, proposal: EvidenceAccessProposal) -> EvidencePlan:
        text = self._combined_text(proposal)
        intent_type = self._intent_type(proposal.intent_type, text)
        repo_walk = self._contains_repo_walk_language(text)
        gaps: list[str] = []
        next_steps: list[str] = []
        resolved_targets: list[EvidencePlanTarget] = []

        if repo_walk:
            gaps.append("Intent contains repo-walk language and is not bounded enough for auto-approval.")
            next_steps.append("Refine the target to a capability, service, component, feature, or explicit file scope.")
        else:
            candidates = self._candidate_paths(proposal.target or "", text)
            for candidate in candidates[:12]:
                resolved_targets.append(EvidencePlanTarget(
                    target_type=self._target_type(candidate),
                    target=candidate,
                    reason=self._target_reason(candidate, proposal),
                    confidence=self._target_confidence(candidate, proposal),
                ))

        evidence_needed = [] if repo_walk else self._evidence_needed(intent_type, proposal, resolved_targets)
        if not resolved_targets:
            gaps.append("No likely repository targets were identified from the current index.")
            next_steps.append("Provide a more specific target name, capability id, service name, or file path.")
        if intent_type == "unknown":
            gaps.append("Intent type could not be classified with high confidence.")
            next_steps.append("State whether the request is for debugging, feature design, architecture review, validation, refactor, or documentation.")

        confidence = self._planning_confidence(
            proposal=proposal,
            intent_type=intent_type,
            resolved_targets=resolved_targets,
            repo_walk=repo_walk,
            gaps=gaps,
        )
        reason = self._confidence_reason(confidence, intent_type, resolved_targets, repo_walk)

        return EvidencePlan(
            proposal_id=proposal.proposal_id,
            intent_type=intent_type,
            objective=proposal.objective,
            reason=proposal.reason,
            target=str(proposal.target or ""),
            desired_outcome=str(proposal.desired_outcome or ""),
            resolved_targets=resolved_targets,
            evidence_needed=evidence_needed,
            planning_confidence=confidence,
            confidence_reason=reason,
            coverage_gaps=gaps,
            recommended_next_steps=next_steps,
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        )

    def approval_recommendation(self, plan: EvidencePlan) -> tuple[str, list[str]]:
        reasons: list[str] = []
        if any("repo-walk" in gap for gap in plan.coverage_gaps):
            return "denied", ["intent_request_contains_repo_walk_language"]
        if plan.planning_confidence >= 0.70:
            return "approved", ["intent_request_passed_planning_litmus_test"]
        reasons.append("intent_request_requires_human_review_due_to_planning_uncertainty")
        return "human_approval_required", reasons

    def _combined_text(self, proposal: EvidenceAccessProposal) -> str:
        return " ".join([
            proposal.objective or "",
            proposal.reason or "",
            proposal.target or "",
            proposal.desired_outcome or "",
        ]).lower()

    def _contains_repo_walk_language(self, text: str) -> bool:
        return any(term in text for term in self.REPO_WALK_TERMS)

    def _intent_type(self, declared: str, text: str) -> str:
        if declared and declared != "unknown":
            return declared
        words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_\.\-]*", text.lower()))
        if words & self.DEBUG_TERMS:
            return "debugging"
        if words & self.FEATURE_TERMS:
            return "feature_design"
        if words & self.VALIDATION_TERMS:
            return "validation"
        if words & self.ARCH_TERMS:
            return "architecture_review"
        if "document" in words or "documentation" in words:
            return "documentation"
        if "refactor" in words or "refactoring" in words:
            return "refactor"
        return "unknown"

    def _candidate_paths(self, target: str, text: str) -> list[str]:
        target = target.strip()
        inventory = self.inventory.inventory()
        paths = list(inventory.paths)
        ranked: list[tuple[int, str]] = []
        terms = self._search_terms(target, text)

        for path in paths:
            if self._skip_path(path):
                continue
            score = 0
            lower_path = path.lower()
            stem = Path(path).stem.lower()
            for term in terms:
                normalized = term.lower().replace(".", "_").replace("-", "_")
                if term.lower() in lower_path:
                    score += 5
                if normalized and normalized in lower_path.replace("-", "_"):
                    score += 4
                if normalized and normalized in stem.replace("-", "_"):
                    score += 3
            target_type = self._target_type(path)
            if target_type in {"service", "route", "model"}:
                score += 3
            if target_type in {"test", "smoke_test"}:
                score += 1
            if lower_path.startswith("services/capabilities/"):
                score += 3
            if lower_path.endswith((".py", ".json", ".yaml", ".yml", ".md")):
                score += 1
            if score > 0:
                ranked.append((score, path))

        ranked.sort(key=lambda item: (-item[0], self._path_priority(item[1]), item[1]))
        return [path for _, path in ranked]

    def _skip_path(self, path: str) -> bool:
        lower_path = path.lower()
        if lower_path.startswith(".ageix/") or lower_path == ".ageix":
            return True
        parts = set(Path(lower_path).parts)
        if parts & self.GENERATED_PATH_PARTS:
            return True
        if any(lower_path.endswith(suffix) for suffix in self.GENERATED_PATH_SUFFIXES):
            return True
        return False

    def _path_priority(self, path: str) -> int:
        kind = self._target_type(path)
        order = {"service": 0, "route": 1, "model": 2, "test": 3, "smoke_test": 4, "file": 5}
        return order.get(kind, 5)

    def _search_terms(self, target: str, text: str) -> list[str]:
        raw_terms = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_\.\-]*", " ".join([target, text])))
        stop = {"need", "understand", "review", "design", "feature", "support", "current", "existing", "code", "repo", "repository", "the", "and", "for", "with", "how", "can", "add", "new", "desired", "outcome"}
        terms = [term for term in raw_terms if len(term) >= 4 and term.lower() not in stop]
        expanded: set[str] = set(terms)
        for term in terms:
            if "." in term:
                expanded.add(term.split(".")[-1])
                expanded.add(term.replace(".", "_"))
            if "_" in term:
                expanded.update(part for part in term.split("_") if len(part) >= 4)
            if "-" in term:
                expanded.update(part for part in term.split("-") if len(part) >= 4)
        return sorted(expanded)

    def _target_type(self, path: str) -> str:
        if path.startswith("tests/"):
            return "test"
        if path.startswith("services/"):
            return "service"
        if path.startswith("models/"):
            return "model"
        if path.startswith("web/routes/"):
            return "route"
        if path.startswith("scripts/Smoke/"):
            return "smoke_test"
        return "file"

    def _target_reason(self, path: str, proposal: EvidenceAccessProposal) -> str:
        kind = self._target_type(path)
        if kind == "test":
            return "Related test coverage may validate the requested intent."
        if kind == "service":
            return "Service implementation may contain the core behavior for the requested intent."
        if kind == "model":
            return "Model/schema evidence may define the contract relevant to the requested intent."
        if kind == "route":
            return "Route evidence may expose the external interface relevant to the requested intent."
        if kind == "smoke_test":
            return "Smoke test evidence may demonstrate end-to-end expected behavior."
        return "Repository path matched the requested intent target."

    def _target_confidence(self, path: str, proposal: EvidenceAccessProposal) -> float:
        target = (proposal.target or "").lower()
        lower_path = path.lower()
        if target and target in lower_path:
            return 0.95
        target_norm = target.replace(".", "_").replace("-", "_")
        if target_norm and target_norm in lower_path.replace("-", "_"):
            return 0.90
        if self._target_type(path) in {"service", "model", "route", "test"}:
            return 0.72
        return 0.60

    def _evidence_needed(self, intent_type: str, proposal: EvidenceAccessProposal, targets: list[EvidencePlanTarget]) -> list[str]:
        needed = ["Primary implementation evidence for approved intent"]
        if any(target.target_type == "model" for target in targets):
            needed.append("Relevant models or schemas")
        else:
            needed.append("Relevant model/schema evidence if available")
        if any(target.target_type == "test" for target in targets):
            needed.append("Related test coverage")
        else:
            needed.append("Related tests or smoke coverage if available")
        if intent_type in {"feature_design", "architecture_review"}:
            needed.append("External interface/route or capability registration evidence")
        if intent_type == "debugging":
            needed.append("Failure-adjacent implementation and focused line/symbol evidence")
        return needed

    def _planning_confidence(self, proposal: EvidenceAccessProposal, intent_type: str, resolved_targets: list[EvidencePlanTarget], repo_walk: bool, gaps: list[str]) -> float:
        if repo_walk:
            return 0.10
        score = 0.18
        if len((proposal.objective or "").split()) >= 4:
            score += 0.12
        if len((proposal.reason or "").split()) >= 5:
            score += 0.12
        if proposal.target:
            score += 0.12
        if proposal.desired_outcome:
            score += 0.08
        if intent_type != "unknown":
            score += 0.10
        if resolved_targets:
            score += min(0.16, 0.03 * len(resolved_targets))
            score += min(0.10, 0.02 * len({target.target_type for target in resolved_targets}))
        else:
            score -= 0.20
        if intent_type == "unknown":
            score -= 0.12
        if gaps:
            score -= min(0.25, 0.08 * len(gaps))

        # 17.0.1 calibration: deterministic search-based planning should not
        # claim certainty. High confidence is reserved for future architecture-map
        # or local-LLM reviewed evidence planning.
        cap = 0.86
        if not any(target.confidence >= 0.90 for target in resolved_targets):
            cap = 0.82
        return round(max(0.0, min(cap, score)), 3)

    def _confidence_reason(self, confidence: float, intent_type: str, targets: list[EvidencePlanTarget], repo_walk: bool) -> str:
        if repo_walk:
            return "Planning confidence is low because the intent appears to request broad repository access."
        if confidence >= 0.80:
            return f"High confidence, but not certain: intent classified as {intent_type} and {len(targets)} likely target(s) were identified by deterministic planning."
        if confidence >= 0.60:
            return f"Moderate confidence: intent classified as {intent_type} with partial deterministic target resolution."
        return "Low confidence: intent or repository target resolution is incomplete."
