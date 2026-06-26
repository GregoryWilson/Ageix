from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


PatchStatus = Literal["stored", "deprecated", "superseded"]
PatchValidationStatus = Literal["not_validated", "validated", "failed"]


class PatchRecord(BaseModel):
    """Governed patch package metadata. PatchWriter only stores; it never applies."""

    patch_id: str = Field(default_factory=lambda: f"PATCH-{uuid4().hex[:12].upper()}")
    patch_name: str = Field(min_length=1)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "patch.create"
    project_id: str = "Ageix"
    summary: str = ""
    status: PatchStatus = "stored"
    validation_status: PatchValidationStatus = "not_validated"
    artifact_id: str | None = None
    patch_path: str
    metadata_path: str
    content_sha256: str
    line_count: int = 0
    byte_count: int = 0
    file_count_estimate: int = 0
    worker_context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "patch_name": self.patch_name,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "project_id": self.project_id,
            "summary": self.summary,
            "status": self.status,
            "validation_status": self.validation_status,
            "artifact_id": self.artifact_id,
            "content_sha256": self.content_sha256,
            "line_count": self.line_count,
            "byte_count": self.byte_count,
            "file_count_estimate": self.file_count_estimate,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "patch_path": self.patch_path,
            "metadata_path": self.metadata_path,
            "worker_context": self.worker_context,
            "metadata": self.metadata,
        }
