from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AgentSession(BaseModel):
    """Long-lived external agent interaction, bounded by a cloud conversation thread."""

    session_id: str
    agent_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    project_id: str | None = None
    last_activity: str | None = None
    updated_at: str | None = None
    capabilities_used: list[str] = Field(default_factory=list)
    active_proposal_id: str | None = None
    active_consultation_ids: list[str] = Field(default_factory=list)
    workflow_stage: str = "session_initialized"
    last_tool: str | None = None
    identity: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
