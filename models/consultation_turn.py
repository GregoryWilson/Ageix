from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.interactive_prompt import InteractivePrompt
from models.participant_response import ParticipantResponse


class ConsultationTurn(BaseModel):
    """One ordered interaction turn inside a consultation session."""

    turn_number: int = Field(ge=1)
    participant_id: str
    status: Literal["pending", "waiting_for_input", "response_recorded", "confidence_satisfied", "max_turns_reached"] = "pending"
    prompt: InteractivePrompt | None = None
    response: ParticipantResponse | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
