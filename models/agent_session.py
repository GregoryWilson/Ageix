from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AgentSession(BaseModel):
    """Long-lived external agent interaction, bounded by a cloud conversation thread."""

    session_id: str
    agent_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    capabilities_used: list[str] = Field(default_factory=list)
