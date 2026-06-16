from __future__ import annotations

from typing import Any

from services.architecture_review_service import ArchitectureReviewService


def run(payload: dict[str, Any]) -> dict[str, Any]:
    review = ArchitectureReviewService().review(
        objective=payload.get("objective", ""),
        repository_evidence=payload.get("repository_evidence", []),
        research_results=payload.get("research_results", []),
        user_answers=payload.get("user_answers", {}),
    )
    return {
        "agent": "cloud_architect",
        "status": "completed",
        "deliverable": review.model_dump(),
        "no_write_confirmation": True,
    }
