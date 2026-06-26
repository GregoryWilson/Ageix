from __future__ import annotations

from pydantic import BaseModel, Field


class CapabilityDefinition(BaseModel):
    """Discoverable contract for a governed Ageix capability."""

    capability_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    access_level: str = Field(min_length=1)
    handler: str = Field(min_length=1)
    description: str = ""
    requires_proposal: bool = False
    requires_consultation: bool = False
    exposed_to_external_agents: bool = True
