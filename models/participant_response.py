from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from models.evidence_request import EvidenceRequest


class ParticipantResponse(BaseModel):
    """Raw participant response before it is normalized into ConsultationResponse."""

    participant_id: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_sufficient: bool = False
    findings: list[str] = Field(default_factory=list)
    requested_followup_evidence: list[EvidenceRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def confidence_satisfies_sufficiency_claim(self) -> "ParticipantResponse":
        threshold = float(self.metadata.get("minimum_evidence_confidence", 0.0))
        if self.evidence_sufficient and self.confidence < threshold:
            raise ValueError("Evidence cannot be marked sufficient below the configured confidence threshold.")
        return self
