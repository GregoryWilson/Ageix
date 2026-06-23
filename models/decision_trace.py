from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DecisionTraceOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    SUPERSEDED = "superseded"
    ABANDONED = "abandoned"
    DEFERRED = "deferred"
    BACKLOG = "backlog"


class DecisionTrace(BaseModel):
    """Append-only historical link between a Chair decision and the evidence used."""

    trace_id: str = Field(default_factory=lambda: f"TRACE-{uuid4().hex[:12].upper()}")
    decision_id: str = Field(default_factory=lambda: f"DEC-{uuid4().hex[:12].upper()}")
    decision_type: str = "governance"
    decision_summary: str = Field(min_length=1)
    outcome: DecisionTraceOutcome
    proposal_id: str | None = None
    evidence_package_ids: list[str] = Field(default_factory=list)
    consultation_ids: list[str] = Field(default_factory=list)
    validation_ids: list[str] = Field(default_factory=list)
    repository_snapshot: dict[str, Any] = Field(default_factory=dict)
    actor_identity: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    outcome_metadata: dict[str, Any] = Field(default_factory=dict)
    related_entities: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def append_only(self) -> bool:
        return True
