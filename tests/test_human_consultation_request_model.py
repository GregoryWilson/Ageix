from __future__ import annotations

from models.human_consultation import (
    HumanConsultationRequest,
    HumanConsultationTargetRecordType,
    HumanConsultationType,
    missing_context_choices,
    missing_evidence_choices,
)


def test_human_consultation_request_includes_constrained_choices() -> None:
    request = HumanConsultationRequest.approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-MODEL",
        question="Approve this proposal?",
        summary="Proposal awaiting Chair decision.",
        evidence_links=["EVPKG-1"],
        trace_ids=["TRACE-1"],
    )

    assert request.consultation_id.startswith("HCONS-")
    assert request.project_id == "Ageix"
    assert request.consultation_type == HumanConsultationType.APPROVAL
    assert request.context.target_record_type == HumanConsultationTargetRecordType.PROPOSAL
    assert request.context.target_record_id == "PROP-HCONS-MODEL"
    assert request.status.value == "pending"
    assert request.system_of_record == "Ageix"
    assert {choice.id for choice in request.choices} >= {"approve", "reject", "add_comment", "other"}


def test_other_choice_requires_freeform_text_and_rationale() -> None:
    request = HumanConsultationRequest.approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-OTHER",
        question="Approve this proposal?",
        summary="Proposal awaiting Chair decision.",
    )

    other = request.choice_by_id("other")

    assert other is not None
    assert other.requires_text is True
    assert other.requires_rationale is True


def test_missing_evidence_and_context_consultations_are_representable() -> None:
    evidence_request = HumanConsultationRequest(
        project_id="Ageix",
        consultation_type=HumanConsultationType.MISSING_EVIDENCE,
        question="What evidence should be used?",
        summary="Missing evidence decision needed.",
        choices=missing_evidence_choices(),
    )
    context_request = HumanConsultationRequest(
        project_id="Ageix",
        consultation_type=HumanConsultationType.MISSING_CONTEXT,
        question="What context should be used?",
        summary="Missing context decision needed.",
        choices=missing_context_choices(),
    )

    assert evidence_request.consultation_type == HumanConsultationType.MISSING_EVIDENCE
    assert context_request.consultation_type == HumanConsultationType.MISSING_CONTEXT
    assert evidence_request.choice_by_id("provide_evidence").requires_text is True
    assert context_request.choice_by_id("provide_context").requires_text is True
