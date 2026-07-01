from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkerLaunchRequest(BaseModel):
    """A bounded request to produce a governed launch handoff, per PROP-934ADA8E57B8.

    A launch request is the input to the Worker Launcher Foundation workflow
    (Admission Ticket -> Launch Profile -> Launch Artifact). It references an
    existing admission ticket and launch profile and names the manual handoff
    adapter to use. It never executes a worker, manages a process, or mutates a
    DevJob — it only requests that Ageix assemble a traceable handoff artifact.
    """

    request_id: str = Field(default_factory=lambda: f"WLREQ-{uuid4().hex[:12].upper()}")
    project_id: str = "Ageix"
    admission_ticket_id: str = Field(min_length=1)
    worker_profile_id: str | None = None
    adapter: str = Field(min_length=1)
    requested_by: str = ""
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "project_id": self.project_id,
            "admission_ticket_id": self.admission_ticket_id,
            "worker_profile_id": self.worker_profile_id,
            "adapter": self.adapter,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
        }
