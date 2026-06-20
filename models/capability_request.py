from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CapabilityRequest(BaseModel):
    """Structured request from an external agent into governed Ageix capabilities."""

    capability_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
