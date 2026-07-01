from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# The three launch states the Worker Execution Bridge may report, per Sprint 21.5.
WorkerLaunchState = Literal["worker_launched", "worker_queued", "worker_launch_failed"]


class WorkerExecutionRecord(BaseModel):
    """A durable, governed record of a Worker Execution Bridge engagement, per
    Sprint 21.5.

    Produced when a valid Chair/delegated directive engages a DevJob-assigned
    worker. It captures the launch state and full traceability across the
    governed chain (DevJob, directive turn, delegation, admission ticket, launch
    artifact, launch provider, and worker session/process reference). When no
    launch provider is available this record IS the durable queued launch
    request. Ageix remains the authoritative store; this record never carries
    worker execution authority itself.
    """

    execution_id: str = Field(default_factory=lambda: f"WEXEC-{uuid4().hex[:12].upper()}")
    project_id: str = "Ageix"
    devjob_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    state: WorkerLaunchState

    admission_ticket_id: str | None = None
    launch_artifact_id: str | None = None
    directive_turn_id: str | None = None
    delegation_id: str | None = None

    launch_provider: str | None = None
    worker_session_ref: dict[str, Any] = Field(default_factory=dict)
    devjob_status_after: str | None = None
    reason: str = ""

    traceability: dict[str, Any] = Field(default_factory=dict)
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "project_id": self.project_id,
            "devjob_id": self.devjob_id,
            "worker_id": self.worker_id,
            "state": self.state,
            "launch_provider": self.launch_provider,
            "admission_ticket_id": self.admission_ticket_id,
            "launch_artifact_id": self.launch_artifact_id,
            "devjob_status_after": self.devjob_status_after,
            "created_at": self.created_at,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "directive_turn_id": self.directive_turn_id,
            "delegation_id": self.delegation_id,
            "worker_session_ref": self.worker_session_ref,
            "reason": self.reason,
            "traceability": self.traceability,
            "created_by": self.created_by,
            "metadata": self.metadata,
        }
