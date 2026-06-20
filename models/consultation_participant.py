from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConsultationParticipant(BaseModel):
    """Registered consultation participant metadata.

    Participants are capabilities exposed to consultation orchestration. They do not
    receive repository access; they only receive brokered session evidence.
    """

    participant_id: str = Field(min_length=1)
    participant_type: Literal["human_interactive", "stub", "future_cloud", "specialist"] = "stub"
    specialties: list[str] = Field(default_factory=list)
    enabled: bool = True
    max_context_tokens: int = 32000
