from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# Temporary bridge (Sprint 25.4.5): default delegations are short-lived and
# single-use. This exists only until the Ageix Human Interface becomes the
# authoritative path for Chair actions, at which point it can be retired.
DEFAULT_DELEGATION_TTL_MINUTES = 30

ChairDelegationStatus = Literal["active", "consumed", "expired", "revoked"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChairDelegation(BaseModel):
    """A narrowly-scoped, time-limited authorization for a delegate to perform a
    single Chair-only action, explicitly granted by the Chair (Greg).

    Temporary bridge, per Sprint 25.4.5. A delegation grants *authority to
    perform one named action*, never identity: the delegate always acts as
    itself. The authorization grant is immutable once created; only its
    consumption status transitions (active -> consumed). Ageix remains the
    authoritative store and all existing governance still applies.
    """

    delegation_id: str = Field(default_factory=lambda: f"CHAIRDLG-{uuid4().hex[:12].upper()}")
    delegator: str = Field(min_length=1)
    delegate: str = Field(min_length=1)
    project_id: str = "Ageix"
    allowed_actions: list[str] = Field(min_length=1)
    status: ChairDelegationStatus = "active"
    single_use: bool = True
    reason: str = ""
    created_at: str = Field(default_factory=lambda: _now().isoformat())
    expires_at: str = Field(
        default_factory=lambda: (_now() + timedelta(minutes=DEFAULT_DELEGATION_TTL_MINUTES)).isoformat()
    )
    consumed_at: str | None = None
    consumed_by: str | None = None
    consumed_for: str | None = None
    lifecycle: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        moment = now or _now()
        try:
            expiry = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        return moment >= expiry

    def authorizes_action(self, action: str) -> bool:
        return str(action or "") in self.allowed_actions

    def to_summary(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "delegator": self.delegator,
            "delegate": self.delegate,
            "project_id": self.project_id,
            "allowed_actions": list(self.allowed_actions),
            "status": self.status,
            "single_use": self.single_use,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "consumed_at": self.consumed_at,
            "consumed_for": self.consumed_for,
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "reason": self.reason,
            "consumed_by": self.consumed_by,
            "lifecycle": self.lifecycle,
            "metadata": self.metadata,
        }
