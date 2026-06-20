from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.consultation_recommendation import ConsultationDisposition
from models.evidence_request import EvidenceRequest


class ConsultationResponse(BaseModel):
    """Normalized advisor response captured inside a consultation session."""

    participant_id: str
    participant_type: Literal["human", "claude", "gpt", "gemini", "future_cloud", "specialist"] = "future_cloud"
    response_type: str = "architecture_review"
    recommendation: str = ""
    confidence: float = 0.0
    disposition: ConsultationDisposition = ConsultationDisposition.CAUTION
    evidence_sufficient: bool = False
    findings: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    requested_followup_evidence: list[EvidenceRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
