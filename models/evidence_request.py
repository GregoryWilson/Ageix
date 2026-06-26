from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceRequest(BaseModel):
    """Structured request for a known evidence dictionary item."""

    request_id: str
    requested_evidence_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    priority: Literal["low", "medium", "high"] = "medium"
    round_number: int = 1
    participant_id: str | None = None
