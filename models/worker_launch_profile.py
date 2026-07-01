from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from models.permission_mode import PermissionMode


class WorkerLaunchProfile(BaseModel):
    """A reusable, governed description of how a worker is admitted, per ADR-0014.

    A launch profile is an admission concept under WorkerAdmission. It captures
    the default permission posture and transport hints for a class of worker.
    It is NOT a launcher: it does not generate URLs, CLI commands, or bootstrap
    prompts, and it never carries authority. Launch adapters (claude_code_web,
    claude_code_cli, etc.) are future, transport-only implementation details and
    are represented here only as non-authoritative metadata hints.
    """

    profile_id: str = Field(default_factory=lambda: f"WLPROFILE-{uuid4().hex[:12].upper()}")
    name: str = Field(min_length=1)
    project_id: str = "Ageix"
    worker_type: str = Field(min_length=1)
    permission_mode: PermissionMode = PermissionMode.SUPERVISED
    description: str = ""
    # Non-authoritative transport hint only (e.g. "claude_code_web"). Not
    # implemented as a launcher in this sprint.
    launch_adapter_hint: str | None = None
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "project_id": self.project_id,
            "worker_type": self.worker_type,
            "permission_mode": self.permission_mode.value,
            "launch_adapter_hint": self.launch_adapter_hint,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "description": self.description,
            "metadata": self.metadata,
        }
