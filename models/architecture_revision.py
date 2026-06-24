from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArchitectureRevisionStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ArchitectureRevisionType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    EXPANSION = "expansion"
    RESTRUCTURE = "restructure"
    DEPRECATION = "deprecation"
    BASELINE = "baseline"


class ArchitectureSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: f"ARCHSNAP-{uuid4().hex[:12].upper()}")
    architecture_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    root: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchitectureRevision(BaseModel):
    revision_id: str = Field(default_factory=lambda: f"ARCHRVSN-{uuid4().hex[:12].upper()}")
    architecture_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    status: ArchitectureRevisionStatus = ArchitectureRevisionStatus.ACTIVE
    revision_type: ArchitectureRevisionType = ArchitectureRevisionType.UPDATE
    summary: str = Field(min_length=1)
    created_by: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    supersedes_revision_id: str | None = None
    snapshot_id: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    decision_trace_id: str | None = None
    evidence_package_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchitectureBaseline(BaseModel):
    architecture_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    active_revision_id: str = Field(min_length=1)
    active_snapshot_id: str = Field(min_length=1)
    active_version: str = Field(min_length=1)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)
