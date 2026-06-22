from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


EvidenceClassification = Literal["primary", "supporting", "validation"]


class PackageFreshnessStatus(str, Enum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    PARTIALLY_MISSING = "partially_missing"
    MISSING = "missing"
    ERROR = "error"


class EvidenceProvenance(BaseModel):
    retrieval_method: str = Field(default="unknown")
    retrieval_source: str = Field(default="evidence_broker")
    retrieval_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    hinted: bool = False
    matched_terms: list[str] = Field(default_factory=list)
    selection_reason: str = Field(default="")
    classification_reason: str = Field(default="")


class EvidencePackageItem(BaseModel):
    path: str = Field(min_length=1)
    classification: EvidenceClassification
    relevance_reason: str = Field(min_length=1)
    retrieval_reason: str = Field(min_length=1)
    hinted: bool = False
    content: str = ""
    content_hash: str = ""
    line_count: int = 0
    returned_line_count: int = 0
    excerpted: bool = False
    start_line: int | None = None
    end_line: int | None = None
    provenance: EvidenceProvenance = Field(default_factory=EvidenceProvenance)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackageFreshness(BaseModel):
    status: PackageFreshnessStatus = PackageFreshnessStatus.UNCHANGED
    stale: bool = False
    freshness_reason: str = "Package evidence still matches the current repository content."
    missing_paths: list[str] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    unchanged_paths: list[str] = Field(default_factory=list)
    last_freshness_check_at: str | None = None


class EvidencePackageIndexEntry(BaseModel):
    package_id: str
    proposal_id: str
    evidence_plan_id: str
    objective: str
    created_at: str
    retrieval_confidence: float = 0.0
    primary_count: int = 0
    supporting_count: int = 0
    validation_count: int = 0
    coverage_gap_count: int = 0
    freshness_status: PackageFreshnessStatus = PackageFreshnessStatus.UNCHANGED
    stale: bool = False
    last_freshness_check_at: str | None = None


class EvidencePackage(BaseModel):
    package_id: str = Field(default_factory=lambda: f"EVPKG-{uuid4().hex[:12].upper()}")
    proposal_id: str
    evidence_plan_id: str
    objective: str = Field(min_length=1)
    intent: str = Field(default="")
    repository_snapshot: dict[str, Any] = Field(default_factory=dict)
    primary_evidence: list[EvidencePackageItem] = Field(default_factory=list)
    supporting_evidence: list[EvidencePackageItem] = Field(default_factory=list)
    validation_evidence: list[EvidencePackageItem] = Field(default_factory=list)
    retrieval_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_reason: str = ""
    coverage_gaps: list[str] = Field(default_factory=list)
    recommended_followup_requests: list[str] = Field(default_factory=list)
    freshness: PackageFreshness | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requester_identity: dict[str, Any] = Field(default_factory=dict)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)

    def all_evidence(self) -> list[EvidencePackageItem]:
        return [*self.primary_evidence, *self.supporting_evidence, *self.validation_evidence]
