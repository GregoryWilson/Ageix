from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ArchitectureReview(BaseModel):
    result_type: Literal["architecture_review"] = "architecture_review"
    confidence: float = Field(ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)
    preferred_patterns: list[str] = Field(default_factory=list)
    dependency_guidance: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    architecture_approved: bool = False

    @model_validator(mode="after")
    def reject_patch_like_payloads(self) -> "ArchitectureReview":
        forbidden = {"changes", "patch", "patch_proposal", "proposed_changes"}
        present = forbidden.intersection(set(self.model_extra or {}))
        if present:
            raise ValueError(f"ArchitectureReview cannot contain patch fields: {sorted(present)}")
        return self

    model_config = {"extra": "forbid"}
