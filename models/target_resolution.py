from __future__ import annotations

from pydantic import BaseModel, Field


class TargetCandidateMatch(BaseModel):
    """Ranked repository candidate for a requested target reference."""

    path: str
    confidence: float
    resolution_method: str
    resolution_reason: str
    matched_signals: list[str] = Field(default_factory=list)


class TargetResolutionEvidence(BaseModel):
    """Explainable evidence for resolving one requested repository target."""

    requested_target: str
    resolved_target: str | None = None
    confidence: float = 0.0
    resolution_method: str = "unresolved"
    resolution_reason: str = "No repository target resolved."
    planner_revisit_required: bool = False
    candidate_matches: list[TargetCandidateMatch] = Field(default_factory=list)
    rejected_candidates: list[TargetCandidateMatch] = Field(default_factory=list)
    target_type: str = "file"


class TargetResolutionResult(BaseModel):
    """Aggregate target grounding result for a planner work packet."""

    resolved_targets: list[str] = Field(default_factory=list)
    unresolved_targets: list[str] = Field(default_factory=list)
    evidence: list[TargetResolutionEvidence] = Field(default_factory=list)
    planner_revisit_required: bool = False

    def as_dict(self) -> dict:
        return self.model_dump()
