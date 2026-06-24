from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ArtifactDeliveryStatus = Literal["completed", "failed"]
ArtifactDeliveryDestination = Literal["local_export"]


class ArtifactDeliveryRecord(BaseModel):
    """Governed record describing delivery of an existing artifact."""

    delivery_id: str = Field(default_factory=lambda: f"DELIV-{uuid4().hex[:12].upper()}")
    artifact_id: str = Field(min_length=1)
    destination: ArtifactDeliveryDestination = "local_export"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "artifact.push"
    project_id: str = "Ageix"
    status: ArtifactDeliveryStatus = "completed"
    delivery_reference: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "artifact_id": self.artifact_id,
            "destination": self.destination,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "project_id": self.project_id,
            "status": self.status,
            "delivery_reference": self.delivery_reference,
            "summary": self.summary,
        }
