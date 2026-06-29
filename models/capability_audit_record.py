from __future__ import annotations

from datetime import datetime, timezone

from typing import Any

from pydantic import BaseModel, Field


class CapabilityAuditRecord(BaseModel):
    session_id: str
    agent_id: str
    capability_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    success: bool
    reason: str = ""
    client_id: str | None = None
    project_id: str | None = None
    participant_id: str | None = None
    agent_role: str | None = None
    model_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
