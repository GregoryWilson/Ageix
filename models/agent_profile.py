from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AgentProfile(BaseModel):
    """Human-seeded participant reputation profile for an external agent."""

    agent_id: str
    display_name: str | None = None
    reputation_level: str = "unknown"
    reputation_score: float = 0.5
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
