from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from models.promotion_readiness import PromotionBlocker


class GovernanceReviewPacket(BaseModel):
    objective: str
    implementation_summary: str
    changed_files: list[str] = Field(default_factory=list)
    requirement_traces: list[dict[str, Any]] = Field(default_factory=list)
    behavioral_evidence: dict[str, Any] = Field(default_factory=dict)
    validation_evidence: dict[str, Any] = Field(default_factory=dict)
    runtime_evidence: dict[str, Any] = Field(default_factory=dict)
    confidence_summary: dict[str, Any] = Field(default_factory=dict)
    blockers: list[PromotionBlocker] = Field(default_factory=list)
    promotion_recommendation: str
