from __future__ import annotations

from pydantic import BaseModel, Field


class PatchProposalNormalizationEvidence(BaseModel):
    raw_field_names: list[str] = Field(default_factory=list)
    normalized_field_names: list[str] = Field(default_factory=list)
    missing_fields_before_normalization: list[str] = Field(default_factory=list)
    missing_fields_after_normalization: list[str] = Field(default_factory=list)
    normalized_from: dict[str, str] = Field(default_factory=dict)
    source_agent: str | None = None
    retry_count: int = 0
