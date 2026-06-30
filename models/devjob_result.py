from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

DevJobResultStatus = Literal["success", "partial", "failed", "blocked"]


class DevJobResult(BaseModel):
    """A reference-only record of work submitted against a DevJob. Holds pointers
    to patches, artifacts, and validation runs; it never carries raw diffs or
    repository content itself."""

    result_id: str = Field(default_factory=lambda: f"DEVJOBRESULT-{uuid4().hex[:12].upper()}")
    job_id: str = Field(min_length=1)
    result_summary: str = ""
    status: DevJobResultStatus = "success"
    public_branch_or_pr: str | None = None
    branch_name: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    patch_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    validation_run_id: str | None = None
    validation_notes: str = ""
    submitted_by: str = ""
    submitted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_summary(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "job_id": self.job_id,
            "result_summary": self.result_summary,
            "status": self.status,
            "patch_id": self.patch_id,
            "validation_run_id": self.validation_run_id,
            "submitted_by": self.submitted_by,
            "submitted_at": self.submitted_at,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "public_branch_or_pr": self.public_branch_or_pr,
            "branch_name": self.branch_name,
            "changed_files": self.changed_files,
            "artifact_ids": self.artifact_ids,
            "validation_notes": self.validation_notes,
        }
