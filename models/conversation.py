from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    """Conversation lifecycle states, per ADR-0016."""

    OPEN = "OPEN"
    ACTIVE = "ACTIVE"
    WAITING_FOR_GREG = "WAITING_FOR_GREG"
    WAITING_FOR_AGENT = "WAITING_FOR_AGENT"
    CONVERGED = "CONVERGED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class Conversation(BaseModel):
    """Governed shared-conversation record, per ADR-0016."""

    conversation_id: str = Field(default_factory=lambda: f"CONV-{uuid4().hex[:12].upper()}")
    project_id: str | None = None
    participants: list[dict[str, Any]] = Field(default_factory=list)
    state: ConversationState = ConversationState.OPEN
    rules_of_engagement: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)
