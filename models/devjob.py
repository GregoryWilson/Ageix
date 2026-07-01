from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

DevJobStatus = Literal[
    "draft",
    "assigned",
    "in_progress",
    "submitted",
    "reviewed",
    "completed",
    "blocked",
    "declined",
    "cancelled",
]


class DevJob(BaseModel):
    """A governed work assignment. Describes what should be implemented, reviewed,
    or investigated. It does not execute work."""

    job_id: str = Field(default_factory=lambda: f"DEVJOB-{uuid4().hex[:12].upper()}")
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    instructions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    prohibited_paths: list[str] = Field(default_factory=list)
    repo_target: str | None = None
    branch_hint: str | None = None
    evidence_package_ids: list[str] = Field(default_factory=list)
    work_context_id: str | None = None
    validation_profile_ids: list[str] = Field(default_factory=list)
    conversation_id: str | None = None
    handoff_id: str | None = None
    origin: str = "manual"
    status: DevJobStatus = "draft"
    created_by: str = ""
    assigned_to: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lifecycle_history: list[dict[str, Any]] = Field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "objective": self.objective,
            "status": self.status,
            "repo_target": self.repo_target,
            "branch_hint": self.branch_hint,
            "origin": self.origin,
            "created_by": self.created_by,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "instructions": self.instructions,
            "acceptance_criteria": self.acceptance_criteria,
            "allowed_paths": self.allowed_paths,
            "prohibited_paths": self.prohibited_paths,
            "evidence_package_ids": self.evidence_package_ids,
            "work_context_id": self.work_context_id,
            "validation_profile_ids": self.validation_profile_ids,
            "conversation_id": self.conversation_id,
            "handoff_id": self.handoff_id,
            "lifecycle_history": self.lifecycle_history,
        }
