from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ResearchClaim(BaseModel):
    claim_id: str
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    category: str = "general"
    implementation_implications: list[str] = Field(default_factory=list)


class ResearchResult(BaseModel):
    result_type: Literal["research_result"] = "research_result"
    confidence: float = Field(ge=0.0, le=1.0)
    claims: list[ResearchClaim] = Field(default_factory=list)
    recommended_patterns: list[str] = Field(default_factory=list)
    dependency_recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_patch_like_payloads(self) -> "ResearchResult":
        forbidden = {"changes", "patch", "patch_proposal", "proposed_changes"}
        present = forbidden.intersection(set(self.model_extra or {}))
        if present:
            raise ValueError(f"ResearchResult cannot contain patch fields: {sorted(present)}")
        return self

    model_config = {"extra": "forbid"}
