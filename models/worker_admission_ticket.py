from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from models.permission_mode import PermissionMode

# Only DEVJOB-* targets are implemented this sprint. CONV-* and INTERACTION-*
# are future-compatible target types that may appear in metadata but are NOT
# implemented and must be denied as unsupported.
SUPPORTED_TARGET_TYPES = {"DEVJOB"}
FUTURE_TARGET_TYPES = {"CONV", "INTERACTION"}

DEFAULT_TICKET_TTL_MINUTES = 30

WorkerAdmissionTicketStatus = Literal["issued", "redeemed", "revoked"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerAdmissionTicket(BaseModel):
    """A scoped, single-use, time-limited admission ticket, per ADR-0014.

    A ticket grants *participation* into one governed DevJob workflow — never
    authority. It carries no DevJob payload; an admitted worker must retrieve
    governed context from Ageix through existing capabilities after admission.
    Ageix remains the authoritative store for DevJob state and assignment.
    """

    ticket_id: str = Field(default_factory=lambda: f"WADMIT-{uuid4().hex[:12].upper()}")
    project_id: str = "Ageix"
    target_type: str = "DEVJOB"
    target_id: str = Field(min_length=1)
    worker_profile_id: str = Field(min_length=1)
    permission_mode: PermissionMode = PermissionMode.SUPERVISED
    # The worker identity the target DevJob is assigned to. Redemption must match
    # this; the ticket cannot broaden who may participate.
    worker_id: str = Field(min_length=1)
    required_next_capability: str = "devjob.get"
    single_use: bool = True
    status: WorkerAdmissionTicketStatus = "issued"
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: _now().isoformat())
    expires_at: str = Field(
        default_factory=lambda: (_now() + timedelta(minutes=DEFAULT_TICKET_TTL_MINUTES)).isoformat()
    )
    redeemed_at: str | None = None
    redeemed_by: str | None = None
    # Lineage when an authorized actor revives/duplicates a stale ticket.
    revived_from_ticket_id: str | None = None
    lifecycle: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        moment = now or _now()
        try:
            expiry = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        return moment >= expiry

    def is_redeemed(self) -> bool:
        return self.status == "redeemed"

    def is_stale(self, *, now: datetime | None = None) -> bool:
        """A ticket is stale once it can no longer be redeemed: expired or spent."""
        return self.is_redeemed() or self.status == "revoked" or self.is_expired(now=now)

    def to_summary(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "project_id": self.project_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "worker_profile_id": self.worker_profile_id,
            "permission_mode": self.permission_mode.value,
            "status": self.status,
            "expires_at": self.expires_at,
            "redeemed_at": self.redeemed_at,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "revived_from_ticket_id": self.revived_from_ticket_id,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "worker_id": self.worker_id,
            "required_next_capability": self.required_next_capability,
            "single_use": self.single_use,
            "redeemed_by": self.redeemed_by,
            "lifecycle": self.lifecycle,
            "metadata": self.metadata,
        }

    def to_admission_context(self) -> dict[str, Any]:
        """Minimal, non-authoritative admission context returned on redemption.

        Deliberately excludes the DevJob payload. The worker must retrieve
        governed context from Ageix via `required_next_capability`.
        """
        return {
            "admission_ticket_id": self.ticket_id,
            "project_id": self.project_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "worker_profile_id": self.worker_profile_id,
            "permission_mode": self.permission_mode.value,
            "required_next_capability": self.required_next_capability,
            "status": self.status,
            "expires_at": self.expires_at,
            "redeemed_at": self.redeemed_at,
            "authoritative_store": "ageix",
        }
