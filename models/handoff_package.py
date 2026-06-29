from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from models.conversation import ConversationState


class HandoffPackage(BaseModel):
    """Governed HANDOFF_PACKAGE artifact summarizing a conversation for handoff, per ADR-0016."""

    handoff_id: str = Field(default_factory=lambda: f"HANDOFF-{uuid4().hex[:12].upper()}")
    conversation_id: str
    participants: list[dict[str, Any]] = Field(default_factory=list)
    rules_of_engagement: dict[str, Any] = Field(default_factory=dict)
    conversation_summary: str = ""
    outstanding_questions: list[dict[str, Any]] = Field(default_factory=list)
    conversation_state: ConversationState
    recent_turns: list[dict[str, Any]] = Field(default_factory=list)
    requested_action: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
