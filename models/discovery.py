from __future__ import annotations

from typing import Literal, Any

from pydantic import BaseModel, Field


class DiscoveryQuestion(BaseModel):
    id: str
    question: str
    allowed_values: list[str] = Field(default_factory=list)
    guidance: str | None = None
    required: bool = True
    resolver: Literal["user", "repository", "research", "cloud_architect", "human_reviewer"] = "user"


class DiscoveryBlocker(BaseModel):
    code: str
    message: str
    resolver: Literal["user", "repository", "research", "cloud_architect", "human_reviewer"]
    question_id: str | None = None


class DiscoveryAnswerValidation(BaseModel):
    question_id: str
    status: Literal["accepted", "accepted_uncertain", "invalid", "guidance_requested", "missing"]
    received: Any = None
    normalized_value: Any = None
    message: str
    guidance: str | None = None
    confidence_delta: float = 0.0


class ArchitectureReviewSignal(BaseModel):
    confidence: float
    review_recommended: bool
    review_required: bool
    preferred_reviewer: Literal["cloud_architect", "human_reviewer", "none"] = "none"
    reasons: list[str] = Field(default_factory=list)


class DiscoveryConfidence(BaseModel):
    objective: float
    repository: float
    external_api: float
    dependency: float
    architecture: float
    overall: float
    required: float = 0.75


class DiscoveryResult(BaseModel):
    status: Literal["ready_for_planning", "discovery_required", "research_pending", "architecture_pending"]
    confidence: DiscoveryConfidence
    blockers: list[DiscoveryBlocker] = Field(default_factory=list)
    questions: list[DiscoveryQuestion] = Field(default_factory=list)
    answer_validation: list[DiscoveryAnswerValidation] = Field(default_factory=list)
    architecture: ArchitectureReviewSignal
    research_required: bool = False
    next_action: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready_for_planning"
