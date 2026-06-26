from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConsultationDisposition(str, Enum):
    """Deterministic consultation outcome states for participants and aggregation."""

    PROCEED = "proceed"
    PROCEED_WITH_RECOMMENDATIONS = "proceed_with_recommendations"
    CAUTION = "caution"
    BLOCKED_INSUFFICIENT_EVIDENCE = "blocked_insufficient_evidence"
    DISAGREEMENT = "disagreement"
    REJECT = "reject"


class ConsultationRecommendation(BaseModel):
    """Structured chair-facing recommendation produced by result aggregation."""

    participant_count: int = 0
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    consensus: ConsultationDisposition = ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE
    summary: str = "No consultation responses were available for aggregation."
    recommendations: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    disagreement_detected: bool = False
    evidence_sufficient: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
