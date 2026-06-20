from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InteractivePrompt(BaseModel):
    """UI-neutral prompt sent to a human or future web client."""

    consultation_id: str
    turn_number: int
    participant_id: str
    title: str
    objective: str = ""
    prompt_text: str
    available_evidence: list[dict[str, Any]] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=lambda: ["recommendation", "confidence"])
    metadata: dict[str, Any] = Field(default_factory=dict)
