from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArchitectureDecisionRecordStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"


class ArchitectureDecisionRecord(BaseModel):
    adr_id: str = Field(default_factory=lambda: f"ADR-{uuid4().hex[:12].upper()}")
    adr_number: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: ArchitectureDecisionRecordStatus = ArchitectureDecisionRecordStatus.PROPOSED

    context: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    alternatives_considered: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    future_considerations: list[str] = Field(default_factory=list)

    proposal_id: str = Field(min_length=1)
    decision_trace_id: str | None = None
    evidence_package_ids: list[str] = Field(default_factory=list)

    architecture_ids: list[str] = Field(default_factory=list)
    revision_ids: list[str] = Field(default_factory=list)

    supersedes_adr_id: str | None = None
    related_adr_ids: list[str] = Field(default_factory=list)

    created_by: str = Field(min_length=1)
    approved_by: str | None = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
