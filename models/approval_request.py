from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ApprovalStatus = Literal["pending", "approved", "denied", "expired"]
ApprovalRequestType = Literal[
    "evidence_expansion",
    "cloud_spend",
    "promotion",
    "repository_access",
    "other",
]


class ApprovalRequest(BaseModel):
    """Persisted human approval requirement for governed Ageix actions."""

    approval_id: str = Field(default_factory=lambda: f"APR-{uuid4().hex[:12].upper()}")
    request_type: ApprovalRequestType = "other"
    proposal_id: str
    reason: str
    requested_by: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str | None = None
    status: ApprovalStatus = "pending"
