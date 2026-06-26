from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PromotionBlockerCode = Literal[
    "LOW_CONFIDENCE",
    "FAILED_RUNTIME_VALIDATION",
    "MISSING_TEST_COVERAGE",
    "MISSING_REQUIREMENT_TRACE",
    "QUALITY_VALIDATION_FAILURE",
    "VALIDATION_EVIDENCE_FAILURE",
    "GOVERNANCE_POLICY_VIOLATION",
]


class PromotionBlocker(BaseModel):
    code: PromotionBlockerCode
    severity: Literal["warning", "error", "critical"] = "error"
    message: str
    remediation: str


class PromotionReadinessResult(BaseModel):
    status: Literal["ready", "conditional", "blocked"]
    confidence: float
    blockers: list[PromotionBlocker] = Field(default_factory=list)
    recommendation: Literal["promote", "review", "reject"]
    human_approval_required: bool = True

    @property
    def passed(self) -> bool:
        return self.status == "ready" and self.recommendation == "promote"
