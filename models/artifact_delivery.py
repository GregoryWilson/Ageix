from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ArtifactDeliveryStatus = Literal["completed", "failed"]
ArtifactDeliveryDestination = Literal["local_export", "requesting_agent"]


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
        """Return summary-first delivery metadata without exposing filesystem paths."""
        payload = {
            "delivery_id": self.delivery_id,
            "artifact_id": self.artifact_id,
            "destination": self.destination,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "project_id": self.project_id,
            "status": self.status,
            "has_delivery_reference": bool(self.delivery_reference),
            "filename": self.metadata.get("filename"),
            "size_bytes": self.metadata.get("size_bytes"),
            "summary": self.summary,
        }
        if self.destination == "requesting_agent":
            payload.update({
                "destination_type": "requesting_agent",
                "agent_id": self.metadata.get("agent_id"),
                "client_id": self.metadata.get("client_id"),
                "provider": self.metadata.get("provider"),
                "consumption_ready": bool(self.metadata.get("consumption_ready")),
            })
        return payload

    def to_detail(self, *, include_reference: bool = False) -> dict[str, Any]:
        """Return delivery details, hiding raw delivery references by default."""
        payload = self.to_summary()
        payload["metadata"] = dict(self.metadata)
        payload["metadata"].pop("source_path", None)
        payload["metadata"].pop("delivery_reference", None)
        if include_reference:
            payload["delivery_reference"] = self.delivery_reference
            payload["metadata"]["source_path"] = self.metadata.get("source_path")
        return payload
