from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CapabilityResponse(BaseModel):
    """Structured response returned by a governed Ageix capability."""

    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
