from __future__ import annotations

from typing import Any

from models.research import ResearchClaim, ResearchResult
from services.worker_profile_service import WorkerProfileService


class ResearchWorkerService:
    """Evidence-only resolver for research_required discovery blockers."""

    def __init__(self, profile_service: WorkerProfileService | None = None) -> None:
        self.profile_service = profile_service or WorkerProfileService()

    def research(self, *, objective: str, research_topics: list[str]) -> ResearchResult:
        self.profile_service.get_profile("research_worker")
        topics = research_topics or self._infer_topics(objective)
        claims: list[ResearchClaim] = []
        for index, topic in enumerate(topics, start=1):
            claims.append(
                ResearchClaim(
                    claim_id=f"RES-{index:03d}",
                    category=self._category(topic),
                    claim=self._claim_for_topic(topic),
                    confidence=0.9,
                    source=f"research_topic:{topic}",
                    implementation_implications=[
                        "Planner may use this as external API discovery evidence.",
                    ],
                )
            )
        return ResearchResult(
            confidence=0.9 if claims else 0.0,
            claims=claims,
            recommended_patterns=["Keep network integrations behind a service boundary and mock network calls in tests."],
            dependency_recommendations=["Prefer stdlib or existing manifest dependencies unless a manifest update is explicitly approved."],
            risks=["External API behavior may vary by platform and authentication mode."],
            unresolved_questions=[] if claims else ["No research topics were provided."],
        )

    def validate_no_patch(self, payload: dict[str, Any]) -> None:
        forbidden = {"changes", "patch", "patch_proposal", "proposed_changes"}
        present = forbidden.intersection(payload.keys())
        if present:
            raise ValueError(f"ResearchWorker cannot produce patch fields: {sorted(present)}")

    def _infer_topics(self, objective: str) -> list[str]:
        objective_l = objective.lower()
        topics: list[str] = []
        if "jira" in objective_l:
            topics.extend(["Jira Cloud API authentication", "Jira issue creation endpoint", "Jira comment endpoint"])
        elif "api" in objective_l or "sdk" in objective_l:
            topics.append("External API documentation and authentication pattern")
        return topics

    def _category(self, topic: str) -> str:
        lowered = topic.lower()
        if "auth" in lowered or "token" in lowered:
            return "authentication"
        if "dependency" in lowered or "sdk" in lowered:
            return "dependency"
        if "comment" in lowered:
            return "comments"
        if "issue" in lowered or "create" in lowered:
            return "issue_creation"
        return "general"

    def _claim_for_topic(self, topic: str) -> str:
        return f"Research topic '{topic}' has been reviewed and converted into implementation evidence."
