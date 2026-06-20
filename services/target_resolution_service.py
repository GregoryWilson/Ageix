from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from models.target_resolution import (
    TargetCandidateMatch,
    TargetResolutionEvidence,
    TargetResolutionResult,
)
from services.controls_service import ControlsService
from services.repository_inventory_service import RepositoryInventoryService


class TargetResolutionService:
    """Deterministically grounds planner target references against repository inventory."""

    DEFAULT_CONTROLS = {
        "enabled": True,
        "minimum_confidence": 0.75,
        "minimum_confidence_gap": 0.15,
        "allow_auto_resolution": True,
        "allow_basename_match": True,
        "allow_directory_similarity": True,
        "allow_resolution_creation": False,
        "planner_revisit_threshold": 0.50,
        "max_candidate_matches": 10,
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)
        self.controls = self._load_controls()
        self.inventory_service = RepositoryInventoryService(self.repo_root)

    def resolve_targets(
        self,
        requested_targets: Iterable[str],
        *,
        repository_evidence: Iterable[str] | None = None,
        dependency_evidence: dict[str, Any] | None = None,
        impact_evidence: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> TargetResolutionResult:
        requested = self._dedupe(self._normalize(path) for path in requested_targets if path)
        if not self.controls.get("enabled", True):
            result = TargetResolutionResult(resolved_targets=requested)
            if persist:
                self.persist_resolution_evidence(result)
            return result

        evidence: list[TargetResolutionEvidence] = []
        resolved_targets: list[str] = []
        unresolved_targets: list[str] = []
        for target in requested:
            item = self.resolve_target(
                target,
                repository_evidence=repository_evidence,
                dependency_evidence=dependency_evidence,
                impact_evidence=impact_evidence,
            )
            evidence.append(item)
            if item.resolved_target:
                resolved_targets.append(item.resolved_target)
            else:
                unresolved_targets.append(item.requested_target)

        result = TargetResolutionResult(
            resolved_targets=self._dedupe(resolved_targets),
            unresolved_targets=self._dedupe(unresolved_targets),
            evidence=evidence,
            planner_revisit_required=any(item.planner_revisit_required for item in evidence),
        )
        if persist:
            self.persist_resolution_evidence(result)
        return result

    def resolve_target(
        self,
        requested_target: str,
        *,
        repository_evidence: Iterable[str] | None = None,
        dependency_evidence: dict[str, Any] | None = None,
        impact_evidence: dict[str, Any] | None = None,
    ) -> TargetResolutionEvidence:
        requested = self._normalize(requested_target)
        inventory = self.inventory_service.inventory()
        paths = inventory.paths
        target_type = "directory" if requested in inventory.directories else "file"

        if requested in paths:
            candidate = TargetCandidateMatch(
                path=requested,
                confidence=1.0,
                resolution_method="exact_path",
                resolution_reason="requested target exactly exists in repository inventory",
                matched_signals=["exact_path"],
            )
            return TargetResolutionEvidence(
                requested_target=requested,
                resolved_target=requested,
                confidence=1.0,
                resolution_method="exact_path",
                resolution_reason=candidate.resolution_reason,
                candidate_matches=[candidate],
                target_type=target_type,
            )

        candidates = self._rank_candidates(
            requested,
            paths,
            repository_evidence=repository_evidence,
            dependency_evidence=dependency_evidence,
            impact_evidence=impact_evidence,
        )
        max_candidates = int(self.controls.get("max_candidate_matches") or 10)
        candidate_matches = candidates[:max_candidates]
        top = candidate_matches[0] if candidate_matches else None
        second = candidate_matches[1] if len(candidate_matches) > 1 else None
        rejected = candidate_matches[1:] if top else []

        if not top:
            return self._failed(requested, [], "No repository candidates matched requested target.")

        min_conf = float(self.controls.get("minimum_confidence") or 0.75)
        gap = float(self.controls.get("minimum_confidence_gap") or 0.0)
        top_gap = top.confidence - (second.confidence if second else 0.0)
        can_auto_resolve = (
            bool(self.controls.get("allow_auto_resolution", True))
            and top.confidence >= min_conf
            and (second is None or top_gap >= gap)
        )
        if can_auto_resolve:
            return TargetResolutionEvidence(
                requested_target=requested,
                resolved_target=top.path,
                confidence=top.confidence,
                resolution_method=top.resolution_method,
                resolution_reason=top.resolution_reason,
                planner_revisit_required=False,
                candidate_matches=candidate_matches,
                rejected_candidates=rejected,
                target_type="directory" if top.path in inventory.directories else "file",
            )

        reason = "candidate confidence below minimum threshold"
        if top.confidence >= min_conf and second is not None and top_gap < gap:
            reason = "top candidate did not exceed next candidate by required confidence gap"
        return TargetResolutionEvidence(
            requested_target=requested,
            resolved_target=None,
            confidence=top.confidence,
            resolution_method="planner_revisit_required",
            resolution_reason=reason,
            planner_revisit_required=True,
            candidate_matches=candidate_matches,
            rejected_candidates=rejected,
            target_type="file",
        )

    def target_resolution_failed_request(self, evidence: TargetResolutionEvidence) -> dict[str, Any]:
        return {
            "result_type": "context_request",
            "reason": "target_resolution_failed",
            "requested_target": evidence.requested_target,
            "recommended_planner_revisit": True,
            "candidate_matches": [candidate.model_dump() for candidate in evidence.candidate_matches],
        }

    def persist_resolution_evidence(self, result: TargetResolutionResult) -> Path:
        path = self.repo_root / ".ageix" / "manifests" / "target_resolution.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.model_dump(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _rank_candidates(
        self,
        requested: str,
        paths: list[str],
        *,
        repository_evidence: Iterable[str] | None,
        dependency_evidence: dict[str, Any] | None,
        impact_evidence: dict[str, Any] | None,
    ) -> list[TargetCandidateMatch]:
        candidates: list[TargetCandidateMatch] = []
        for path in paths:
            candidate = self._score_candidate(
                requested,
                path,
                repository_evidence=set(self._normalize(item) for item in (repository_evidence or [])),
                dependency_paths=self._evidence_paths(dependency_evidence or {}),
                impact_paths=self._evidence_paths(impact_evidence or {}),
            )
            if candidate.confidence >= float(self.controls.get("planner_revisit_threshold") or 0.50):
                candidates.append(candidate)
        return sorted(candidates, key=lambda item: (-item.confidence, item.path))

    def _score_candidate(
        self,
        requested: str,
        path: str,
        *,
        repository_evidence: set[str],
        dependency_paths: set[str],
        impact_paths: set[str],
    ) -> TargetCandidateMatch:
        requested_path = Path(requested)
        candidate_path = Path(path)
        requested_name = requested_path.name
        candidate_name = candidate_path.name
        requested_stem = requested_path.stem
        candidate_stem = candidate_path.stem
        requested_dir = str(requested_path.parent).replace("\\", "/") if str(requested_path.parent) != "." else ""
        candidate_dir = str(candidate_path.parent).replace("\\", "/") if str(candidate_path.parent) != "." else ""

        signals: list[str] = []
        method = "similarity"
        reason = "repository candidate similarity"
        score = 0.0

        if requested_name == candidate_name:
            score = 0.95
            method = "exact_filename"
            reason = "candidate filename exactly matches requested filename"
            signals.append("exact_filename")
        elif self.controls.get("allow_basename_match", True) and requested_stem and requested_stem == candidate_stem:
            score = 0.85
            method = "basename_match"
            reason = "candidate basename matches requested basename"
            signals.append("basename_match")
        else:
            basename_similarity = SequenceMatcher(None, requested_stem.lower(), candidate_stem.lower()).ratio() if requested_stem and candidate_stem else 0.0
            if self.controls.get("allow_basename_match", True) and basename_similarity >= 0.72:
                score = max(score, 0.55 + (basename_similarity - 0.72) * 0.5)
                method = "basename_similarity"
                reason = "candidate basename is similar to requested basename"
                signals.append("basename_similarity")

        if self.controls.get("allow_directory_similarity", True) and requested_dir and candidate_dir:
            dir_similarity = SequenceMatcher(None, requested_dir.lower(), candidate_dir.lower()).ratio()
            if requested_dir == candidate_dir:
                score += 0.10
                signals.append("same_directory")
            elif dir_similarity >= 0.60:
                score = max(score, 0.60 + (dir_similarity - 0.60) * 0.25)
                signals.append("directory_similarity")
                if method == "similarity":
                    method = "directory_similarity"
                    reason = "candidate directory is similar to requested directory"

        if path in repository_evidence:
            score += 0.05
            signals.append("repository_evidence_relevance")
        if path in dependency_paths:
            score += 0.03
            signals.append("dependency_relevance")
        if path in impact_paths:
            score += 0.02
            signals.append("impact_relevance")

        if path.startswith("tests/") and not requested.startswith("tests/"):
            score -= 0.10
            signals.append("test_file_penalty")

        score = max(0.0, min(1.0, round(score, 4)))
        return TargetCandidateMatch(
            path=path,
            confidence=score,
            resolution_method=method,
            resolution_reason=reason,
            matched_signals=signals,
        )

    def _evidence_paths(self, data: dict[str, Any]) -> set[str]:
        paths: set[str] = set()
        def visit(value: Any) -> None:
            if isinstance(value, str):
                normalized = self._normalize(value)
                if "/" in normalized or "." in Path(normalized).name:
                    paths.add(normalized)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
            elif isinstance(value, dict):
                for item in value.values():
                    visit(item)
        visit(data)
        return paths

    def _failed(self, requested: str, candidates: list[TargetCandidateMatch], reason: str) -> TargetResolutionEvidence:
        return TargetResolutionEvidence(
            requested_target=requested,
            resolved_target=None,
            confidence=candidates[0].confidence if candidates else 0.0,
            resolution_method="planner_revisit_required",
            resolution_reason=reason,
            planner_revisit_required=True,
            candidate_matches=candidates,
        )

    def _load_controls(self) -> dict[str, Any]:
        raw = ControlsService(self.repo_root).get_raw_config().get("target_resolution", {})
        merged = dict(self.DEFAULT_CONTROLS)
        if isinstance(raw, dict):
            merged.update(raw)
        return merged

    def _normalize(self, path_text: str) -> str:
        normalized = str(path_text).replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.rstrip("/")

    def _dedupe(self, values: Iterable[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            text = self._normalize(value)
            if text and text not in output:
                output.append(text)
        return output
