from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    AWAITING_EVIDENCE = "awaiting_evidence"
    AWAITING_CONSULTATION = "awaiting_consultation"
    CONSULTATION_SUBMITTED = "consultation_submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    DENIED = "denied"
    CLOSED = "closed"


class ProposalType(str, Enum):
    ARCHITECTURE = "architecture"
    IMPLEMENTATION = "implementation"
    GOVERNANCE = "governance"
    RISK = "risk"
    INVESTIGATION = "investigation"
    VALIDATION = "validation"


class Proposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"PROP-{uuid4().hex[:12].upper()}")
    proposal_version: int = 1
    parent_proposal_id: str | None = None
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    proposal_type: ProposalType = ProposalType.INVESTIGATION
    status: ProposalStatus = ProposalStatus.SUBMITTED
    created_at: str = ""
    updated_at: str = ""
    linked_evidence: list[str] = Field(default_factory=list)
    linked_consultations: list[str] = Field(default_factory=list)
    linked_execution_evidence: list[str] = Field(default_factory=list)
    required_consultations: list[str] = Field(default_factory=list)
    accepted_consultations: list[str] = Field(default_factory=list)
    rejected_consultations: list[str] = Field(default_factory=list)
    satisfied_consultations: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposalEvaluationResult(BaseModel):
    proposal_id: str
    disposition: str
    evidence_sufficient: bool = False
    consultation_required: bool = False
    approval_required: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    required_consultations: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
