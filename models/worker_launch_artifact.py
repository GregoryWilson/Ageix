from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from models.permission_mode import PermissionMode

# Actions the Worker Launcher Foundation explicitly does NOT perform. These are
# surfaced verbatim in every launch artifact so the governance boundary is
# visible to whoever receives the handoff. This sprint produces a handoff only.
LAUNCHER_DENIED_ACTIONS = [
    "direct_worker_execution",
    "local_process_management",
    "stdout_stderr_capture",
    "execution_callbacks",
    "validation_worker_sequencing",
    "patch_application",
    "devjob_execution_change",
    "devjob_completion",
    "chair_approval_bypass",
    "project_context_bypass",
    "governed_artifact_boundary_bypass",
]


class WorkerLaunchArtifact(BaseModel):
    """A governed, non-authoritative launch handoff artifact, per PROP-934ADA8E57B8.

    Produced by the Worker Launcher Foundation as the final step of the
    Admission Ticket -> Launch Profile -> Launch Artifact workflow. It captures
    the manual handoff instructions, the authority scope, the explicitly denied
    actions, and full traceability. It never implies that downstream work was
    executed: `execution_performed` is always False and `non_authoritative` is
    always True. Ageix remains the authoritative store.
    """

    launch_artifact_id: str = Field(default_factory=lambda: f"WLAUNCH-{uuid4().hex[:12].upper()}")
    project_id: str = "Ageix"
    request_id: str = Field(min_length=1)
    admission_ticket_id: str = Field(min_length=1)
    worker_profile_id: str = Field(min_length=1)
    adapter: str = Field(min_length=1)

    target_type: str = "DEVJOB"
    target_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    permission_mode: PermissionMode = PermissionMode.SUPERVISED
    required_next_capability: str = "devjob.get"

    handoff_instructions: list[str] = Field(default_factory=list)
    launch_reference: dict[str, Any] = Field(default_factory=dict)
    denied_actions: list[str] = Field(default_factory=lambda: list(LAUNCHER_DENIED_ACTIONS))
    authority_scope: dict[str, Any] = Field(default_factory=dict)
    traceability: dict[str, Any] = Field(default_factory=dict)

    non_authoritative: bool = True
    execution_performed: bool = False

    governed_artifact_id: str | None = None
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "launch_artifact_id": self.launch_artifact_id,
            "project_id": self.project_id,
            "admission_ticket_id": self.admission_ticket_id,
            "worker_profile_id": self.worker_profile_id,
            "adapter": self.adapter,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "permission_mode": self.permission_mode.value,
            "non_authoritative": self.non_authoritative,
            "execution_performed": self.execution_performed,
            "governed_artifact_id": self.governed_artifact_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "request_id": self.request_id,
            "worker_id": self.worker_id,
            "required_next_capability": self.required_next_capability,
            "handoff_instructions": self.handoff_instructions,
            "launch_reference": self.launch_reference,
            "denied_actions": self.denied_actions,
            "authority_scope": self.authority_scope,
            "traceability": self.traceability,
            "metadata": self.metadata,
        }
