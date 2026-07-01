from __future__ import annotations

import re
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


HUMAN_CONSULTATION_ID_PATTERN = r"^HCONS-[A-F0-9]{12}$"


def generate_human_consultation_id() -> str:
    return f"HCONS-{uuid4().hex[:12].upper()}"


def is_valid_human_consultation_id(consultation_id: str) -> bool:
    return bool(re.fullmatch(HUMAN_CONSULTATION_ID_PATTERN, str(consultation_id or "")))


class HumanConsultationType(str, Enum):
    APPROVAL = "approval"
    MISSING_EVIDENCE = "missing_evidence"
    MISSING_CONTEXT = "missing_context"
    AMBIGUITY = "ambiguity"
    PRIORITIZATION = "prioritization"
    RISK_ACCEPTANCE = "risk_acceptance"
    ARCHITECTURE_DECISION = "architecture_decision"
    OTHER = "other"


class HumanConsultationTargetRecordType(str, Enum):
    PROPOSAL = "proposal"
    ADR = "adr"
    EVIDENCE = "evidence"
    VALIDATION = "validation"
    WORK_CONTEXT = "work_context"
    OTHER = "other"


class HumanConsultationStatus(str, Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    CANCELLED = "cancelled"


class HumanConsultationContext(BaseModel):
    target_record_type: HumanConsultationTargetRecordType = HumanConsultationTargetRecordType.OTHER
    target_record_id: str = ""
    evidence_links: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)


class HumanConsultationChoice(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    requires_rationale: bool = False
    requires_text: bool = False


class HumanConsultationRequest(BaseModel):
    consultation_id: str = Field(default_factory=generate_human_consultation_id, pattern=HUMAN_CONSULTATION_ID_PATTERN)
    project_id: str = Field(min_length=1)
    consultation_type: HumanConsultationType
    question: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    context: HumanConsultationContext = Field(default_factory=HumanConsultationContext)
    choices: list[HumanConsultationChoice] = Field(default_factory=list)
    status: HumanConsultationStatus = HumanConsultationStatus.PENDING
    system_of_record: str = "Ageix"
    created_at: str = ""
    updated_at: str = ""
    answered_at: str | None = None
    selected_choice_id: str | None = None
    rationale: str | None = None
    freeform_text: str | None = None
    response_result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def approval_request(
        cls,
        *,
        project_id: str,
        target_record_type: str,
        target_record_id: str,
        question: str,
        summary: str,
        evidence_links: list[str] | None = None,
        trace_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "HumanConsultationRequest":
        return cls(
            project_id=project_id,
            consultation_type=HumanConsultationType.APPROVAL,
            question=question,
            summary=summary,
            context=HumanConsultationContext(
                target_record_type=HumanConsultationTargetRecordType(target_record_type),
                target_record_id=target_record_id,
                evidence_links=list(evidence_links or []),
                trace_ids=list(trace_ids or []),
            ),
            choices=approval_choices(),
            metadata=dict(metadata or {}),
        )

    def choice_by_id(self, choice_id: str) -> HumanConsultationChoice | None:
        normalized = str(choice_id or "").strip().lower().replace("-", "_").replace(" ", "_")
        for choice in self.choices:
            if choice.id == normalized:
                return choice
        return None


def approval_choices() -> list[HumanConsultationChoice]:
    return [
        HumanConsultationChoice(id="approve", label="Approve", requires_rationale=True),
        HumanConsultationChoice(id="reject", label="Reject", requires_rationale=True),
        HumanConsultationChoice(id="add_comment", label="Add comment", requires_rationale=True),
        HumanConsultationChoice(id="other", label="Other...", requires_text=True, requires_rationale=True),
    ]


def missing_evidence_choices() -> list[HumanConsultationChoice]:
    return [
        HumanConsultationChoice(id="provide_evidence", label="Provide evidence", requires_text=True, requires_rationale=True),
        HumanConsultationChoice(id="proceed_without_evidence", label="Proceed without evidence", requires_rationale=True),
        HumanConsultationChoice(id="cancel", label="Cancel", requires_rationale=True),
        HumanConsultationChoice(id="other", label="Other...", requires_text=True, requires_rationale=True),
    ]


def missing_context_choices() -> list[HumanConsultationChoice]:
    return [
        HumanConsultationChoice(id="provide_context", label="Provide context", requires_text=True, requires_rationale=True),
        HumanConsultationChoice(id="use_available_context", label="Use available context", requires_rationale=True),
        HumanConsultationChoice(id="cancel", label="Cancel", requires_rationale=True),
        HumanConsultationChoice(id="other", label="Other...", requires_text=True, requires_rationale=True),
    ]
