from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

DevJobEventType = Literal[
    "execution_blocked",
    "execution_failed",
    "execution_warning",
    # Worker Execution Bridge launch states (Sprint 21.5). Surfaced on the
    # DevJob so worker activation outcomes are visible through its lifecycle.
    "worker_launched",
    "worker_queued",
    "worker_launch_failed",
    # Governed non-transition DevJob events from the lifecycle hardening. These
    # record scope, review, git-sync, and validation-waiver actions through the
    # same append-only event surface (Sprint 21.1/21.5 event API).
    "scope_revision",
    "review_submitted",
    "git_sync_attached",
    "validation_waiver",
]


class DevJobEvent(BaseModel):
    """An append-only audit event attached to a DevJob.

    Used to surface blocked, failed, or degraded DevWorker execution conditions
    through an existing DevJob surface without changing lifecycle state or
    authority. Events are never mutated once written.
    """

    event_id: str = Field(default_factory=lambda: f"DEVJOBEVENT-{uuid4().hex[:12].upper()}")
    job_id: str = Field(min_length=1)
    event_type: DevJobEventType
    summary: str = ""
    reason: str | None = None
    actor_id: str = ""
    actor_role: str | None = None
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
