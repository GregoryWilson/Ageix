from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ArtifactStatus = Literal["available", "missing", "superseded", "deprecated"]


class ArtifactReference(BaseModel):
    """Metadata-only relationship from an artifact to another governed object."""

    reference_type: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    relationship: str = "related"


class ArtifactRecord(BaseModel):
    """Governed registry record for a generated Ageix artifact."""

    artifact_id: str = Field(default_factory=lambda: f"ART-{uuid4().hex[:12].upper()}")
    artifact_category: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = Field(min_length=1)
    project_id: str = "Ageix"
    source_id: str | None = None
    summary: str = ""
    status: ArtifactStatus = "available"
    path: str | None = None
    references: list[ArtifactReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_category": self.artifact_category,
            "artifact_type": self.artifact_type,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "project_id": self.project_id,
            "source_id": self.source_id,
            "summary": self.summary,
            "status": self.status,
            "reference_count": len(self.references),
        }
