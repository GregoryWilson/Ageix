from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from models.agent_role import AgentRole


class TurnType(str, Enum):
    """Turn classification for shared conversation turns, per ADR-0016."""

    STATEMENT = "STATEMENT"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    DIRECTIVE = "DIRECTIVE"
    SPECULATION = "SPECULATION"
    OBSERVATION = "OBSERVATION"
    NO_COMMENT = "NO_COMMENT"
    ABSTAIN = "ABSTAIN"
    ESCALATE = "ESCALATE"


class ConversationTurn(BaseModel):
    """One immutable, append-only turn in a shared conversation, per ADR-0016."""

    turn_id: str = Field(default_factory=lambda: f"TURN-{uuid4().hex[:12].upper()}")
    conversation_id: str
    sequence_number: int = Field(ge=1)
    speaker_client_id: str
    speaker_agent_role: AgentRole
    speaker_session_id: str
    model_id: str
    turn_type: TurnType
    directed_at: str | None = None
    confidence: float = Field(ge=0.0, le=10.0)
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
