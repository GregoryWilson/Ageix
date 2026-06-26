from __future__ import annotations

from pathlib import Path
from typing import Any

from services.controls_service import ControlsService


class ConfidenceScoringService:
    """Calculates confidence from governance-controlled validation weights."""

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.controls = ControlsService(Path(repo_root)).promotion_confidence

    def summarize(
        self,
        *,
        proposal_quality: Any,
        requirement_trace: Any,
        behavior_verification: Any,
        validation_evidence: Any,
        runtime_execution: Any,
    ) -> dict[str, Any]:
        component_scores = {
            "proposal_quality": self._score_passed(proposal_quality),
            "requirement_traceability": self._score_passed(requirement_trace),
            "behavioral_verification": self._score_passed(behavior_verification),
            "validation_evidence": self._score_passed(validation_evidence),
            "runtime_execution": self._score_passed(runtime_execution),
        }
        weights = self.controls.weights or {}
        weighted_total = sum(component_scores[name] * float(weights.get(name, 0.0)) for name in component_scores)
        weight_total = sum(float(weights.get(name, 0.0)) for name in component_scores)
        overall = weighted_total / weight_total if weight_total else 0.0
        return {
            "enabled": self.controls.enabled,
            "minimum_confidence": self.controls.minimum_confidence,
            "overall_confidence": round(overall, 4),
            "rating": self._rating(overall),
            "meets_minimum": overall >= self.controls.minimum_confidence,
            "weights": dict(weights),
            "components": component_scores,
        }

    def _score_passed(self, value: Any) -> float:
        if value is None:
            return 0.0
        passed = getattr(value, "passed", None)
        if isinstance(passed, bool):
            return 1.0 if passed else 0.0
        status = getattr(value, "status", None)
        if status is None and isinstance(value, dict):
            status = value.get("status")
        return 1.0 if str(status).lower() in {"pass", "passed"} else 0.0

    def _rating(self, score: float) -> str:
        ratings = self.controls.ratings or {}
        if score >= float(ratings.get("high", 0.90)):
            return "high"
        if score >= float(ratings.get("medium", 0.75)):
            return "medium"
        if score >= float(ratings.get("low", 0.50)):
            return "low"
        return "untrusted"
