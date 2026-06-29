from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from models.agent_role import AgentRole


class ConversationEvent(BaseModel):
    """A governance event recorded alongside a conversation, per ADR-0016.

    Governance actions (approvals, commissions) taken by the Chair are
    recorded as events, distinct from the immutable turn record, since they
    are not contributions to the discussion itself.
    """

    event_id: str = Field(default_factory=lambda: f"EVENT-{uuid4().hex[:12].upper()}")
    conversation_id: str
    event_type: str
    governance_action_id: str
    actor_agent_role: AgentRole
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
