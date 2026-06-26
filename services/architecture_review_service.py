from __future__ import annotations

from typing import Any

from models.architecture_review import ArchitectureReview
from models.research import ResearchResult
from services.worker_profile_service import WorkerProfileService


class ArchitectureReviewService:
    """Guidance-only resolver for architecture_review_required discovery blockers."""

    def __init__(self, profile_service: WorkerProfileService | None = None) -> None:
        self.profile_service = profile_service or WorkerProfileService()

    def review(
        self,
        *,
        objective: str,
        repository_evidence: list[dict[str, Any]] | None = None,
        research_results: list[ResearchResult] | None = None,
        user_answers: dict[str, Any] | None = None,
    ) -> ArchitectureReview:
        self.profile_service.get_profile("cloud_architect")
        repository_evidence = repository_evidence or []
        research_results = research_results or []
        user_answers = user_answers or {}
        recommendations = ["Implement new integrations as a Worker + Service pair with deterministic service tests."]
        preferred_patterns = ["Reuse existing Ageix service/model boundaries and controls governance patterns."]
        dependency_guidance = ["Keep secrets in environment variables and policy in controls.json."]
        risks = []
        confidence = 0.85
        if not research_results and self._needs_external_research(objective):
            confidence = 0.65
            risks.append("External API evidence is missing, so architecture approval is withheld.")
        if repository_evidence:
            confidence = max(confidence, 0.88)
        if user_answers:
            confidence = max(confidence, 0.86)
        return ArchitectureReview(
            confidence=round(confidence, 2),
            recommendations=recommendations,
            preferred_patterns=preferred_patterns,
            dependency_guidance=dependency_guidance,
            risks=risks,
            architecture_approved=confidence >= 0.75 and not risks,
        )

    def validate_no_patch(self, payload: dict[str, Any]) -> None:
        forbidden = {"changes", "patch", "patch_proposal", "proposed_changes"}
        present = forbidden.intersection(payload.keys())
        if present:
            raise ValueError(f"CloudArchitect cannot produce patch fields: {sorted(present)}")

    def _needs_external_research(self, objective: str) -> bool:
        objective_l = objective.lower()
        return any(term in objective_l for term in ["api", "sdk", "jira", "octoprint", "github", "external"])
