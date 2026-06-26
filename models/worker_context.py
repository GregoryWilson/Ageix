from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkerContext(BaseModel):
    """Lightweight execution envelope shared by governed Ageix workers."""

    worker: str = Field(min_length=1)
    workflow_id: str = Field(default_factory=lambda: f"WORK-{uuid4().hex[:12].upper()}")
    project_id: str = "Ageix"
    agent_id: str = "unknown"
    client_id: str | None = None
    session_id: str | None = None
    request_id: str = Field(default_factory=lambda: f"REQ-{uuid4().hex[:12].upper()}")
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "workflow_id": self.workflow_id,
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "client_id": self.client_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "started_at": self.started_at,
        }
