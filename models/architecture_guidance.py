from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArchitectureGuidanceStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"


class ArchitecturePrinciple(BaseModel):
    principle_id: str = Field(default_factory=lambda: f"ARCHPRIN-{uuid4().hex[:12].upper()}")
    principle_number: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    rationale: str = ""
    status: ArchitectureGuidanceStatus = ArchitectureGuidanceStatus.PROPOSED
    scope: str = "project"

    proposal_id: str = Field(min_length=1)
    decision_trace_id: str | None = None
    evidence_package_ids: list[str] = Field(default_factory=list)

    architecture_ids: list[str] = Field(default_factory=list)
    adr_ids: list[str] = Field(default_factory=list)
    revision_ids: list[str] = Field(default_factory=list)

    supersedes_principle_id: str | None = None
    related_principle_ids: list[str] = Field(default_factory=list)

    created_by: str = Field(min_length=1)
    approved_by: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchitectureIntent(BaseModel):
    intent_id: str = Field(default_factory=lambda: f"ARCHINTENT-{uuid4().hex[:12].upper()}")
    intent_number: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    details: str = ""
    status: ArchitectureGuidanceStatus = ArchitectureGuidanceStatus.PROPOSED
    scope: str = "project"
    future_considerations: list[str] = Field(default_factory=list)

    proposal_id: str = Field(min_length=1)
    decision_trace_id: str | None = None
    evidence_package_ids: list[str] = Field(default_factory=list)

    architecture_ids: list[str] = Field(default_factory=list)
    adr_ids: list[str] = Field(default_factory=list)
    principle_ids: list[str] = Field(default_factory=list)
    revision_ids: list[str] = Field(default_factory=list)

    supersedes_intent_id: str | None = None
    related_intent_ids: list[str] = Field(default_factory=list)

    created_by: str = Field(min_length=1)
    approved_by: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
