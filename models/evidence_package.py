from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


EvidenceClassification = Literal["primary", "supporting", "validation"]


class EvidencePackageItem(BaseModel):
    path: str = Field(min_length=1)
    classification: EvidenceClassification
    relevance_reason: str = Field(min_length=1)
    retrieval_reason: str = Field(min_length=1)
    hinted: bool = False
    content: str = ""
    line_count: int = 0
    returned_line_count: int = 0
    excerpted: bool = False
    start_line: int | None = None
    end_line: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidencePackage(BaseModel):
    package_id: str = Field(default_factory=lambda: f"EVPKG-{uuid4().hex[:12].upper()}")
    proposal_id: str
    evidence_plan_id: str
    objective: str = Field(min_length=1)
    intent: str = Field(default="")
    primary_evidence: list[EvidencePackageItem] = Field(default_factory=list)
    supporting_evidence: list[EvidencePackageItem] = Field(default_factory=list)
    validation_evidence: list[EvidencePackageItem] = Field(default_factory=list)
    retrieval_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_reason: str = ""
    coverage_gaps: list[str] = Field(default_factory=list)
    recommended_followup_requests: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requester_identity: dict[str, Any] = Field(default_factory=dict)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
