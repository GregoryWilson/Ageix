from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from models.agent_role import AgentRole


class ConversationParticipant(BaseModel):
    """Registered participant of a shared conversation, keyed by composite identity tuple, per ADR-0016."""

    client_id: str
    agent_role: AgentRole
    session_id: str
    confidence_threshold: float
    active: bool = True
    joined_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
