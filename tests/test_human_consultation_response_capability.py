from __future__ import annotations

from pathlib import Path

import pytest

from models.architecture_decision_record import ArchitectureDecisionRecordStatus
from models.capability_request import CapabilityRequest
from models.human_consultation import HumanConsultationRequest, HumanConsultationType, missing_evidence_choices
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.capability_execution_service import CapabilityExecutionService
from services.human_consultation_service import HumanConsultationService
from services.proposal_service import ProposalService


def _proposal(tmp_path: Path, proposal_id: str) -> None:
    ProposalService(tmp_path).create_proposal(Proposal(
        proposal_id=proposal_id,
        project_id="Ageix",
        session_id="session-1",
        agent_id="lex",
        objective="Review human consultation routing.",
        proposal_type=ProposalType.IMPLEMENTATION,
        status=ProposalStatus.SUBMITTED,
        metadata={},
    ))


def _chair_args(consultation_id: str, choice: str = "approve", rationale: str = "Chair rationale.") -> dict:
    return {
        "project_id": "Ageix",
        "consultation_id": consultation_id,
        "selected_choice_id": choice,
        "rationale": rationale,
        "freeform_text": "",
        "client_id": "human_interface",
        "provider": "human_interface",
        "agent_role": "ageix.chair",
    }


def _execute(tmp_path: Path, arguments: dict) -> dict:
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="human.consultation.respond",
        session_id="human-consultation-test",
        agent_id="chair",
        arguments=arguments,
    ))
    return {"success": response.success, "result": response.result, "error": response.error, "metadata": response.metadata}


def _invalid_consultation_ids() -> list[str]:
    parent = ".."
    slash = "/"
    return [
        parent + slash + "foo",
        "HCONS-" + parent + slash + parent + slash,
        "HCONS-123",
        "HCONS-ABC",
        "HCONS-ABCDEFGHIJKL",
        "HCONS-abcdef123456",
    ]


@pytest.mark.parametrize("consultation_id", _invalid_consultation_ids())
def test_invalid_consultation_id_rejected_before_filesystem_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    consultation_id: str,
) -> None:
    service = HumanConsultationService(tmp_path)

    def fail_get_request(_consultation_id: str) -> HumanConsultationRequest:
        raise AssertionError("filesystem lookup attempted before consultation_id validation")

    def fail_path(_consultation_id: str) -> Path:
        raise AssertionError("path construction attempted before consultation_id validation")

    monkeypatch.setattr(service, "get_request", fail_get_request)
    monkeypatch.setattr(service, "_path", fail_path)

    result = service.respond(_chair_args(consultation_id))

    assert result["success"] is False
    assert result["error"] == "invalid_consultation_id"
    assert not (tmp_path / ".ageix" / "human_consultations").exists()


def test_invalid_consultation_id_does_not_mutate_existing_consultation_lifecycle(tmp_path: Path) -> None:
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-ID-MUTATION",
        question="Approve?",
        summary="Approval needed.",
    )
    before = service.get_request(consultation.consultation_id).model_dump(mode="json")

    result = service.respond(_chair_args("HCONS-abcdef123456"))

    assert result["success"] is False
    assert result["error"] == "invalid_consultation_id"
    assert service.get_request(consultation.consultation_id).model_dump(mode="json") == before


def test_invalid_choice_is_rejected(tmp_path: Path) -> None:
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-BAD-CHOICE",
        question="Approve?",
        summary="Approval needed.",
    )

    result = service.respond(_chair_args(consultation.consultation_id, choice="invalid"))

    assert result["success"] is False
    assert result["error"] == "invalid_choice"
    assert service.get_request(consultation.consultation_id).status.value == "pending"


def test_missing_rationale_is_rejected_when_required(tmp_path: Path) -> None:
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-RATIONALE",
        question="Approve?",
        summary="Approval needed.",
    )

    result = service.respond(_chair_args(consultation.consultation_id, rationale=""))

    assert result["success"] is False
    assert result["error"] == "rationale_required"


def test_other_requires_freeform_text_and_rationale(tmp_path: Path) -> None:
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-OTHER",
        question="Approve?",
        summary="Approval needed.",
    )

    result = service.respond(_chair_args(consultation.consultation_id, choice="other"))

    assert result["success"] is False
    assert result["error"] == "freeform_text_required"


def test_non_chair_role_cannot_submit_state_changing_response(tmp_path: Path) -> None:
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-NONCHAIR",
        question="Approve?",
        summary="Approval needed.",
    )
    args = _chair_args(consultation.consultation_id)
    args["agent_role"] = "lex"

    result = service.respond(args)

    assert result["success"] is False
    assert result["error"] == "authorization_failure"
    assert service.get_request(consultation.consultation_id).status.value == "pending"


def test_proposal_approval_consultation_routes_to_existing_proposal_approval_capability(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-HCONS-APPROVE")
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="proposal",
        target_record_id="PROP-HCONS-APPROVE",
        question="Approve proposal?",
        summary="Proposal approval requested.",
    )

    result = _execute(tmp_path, _chair_args(consultation.consultation_id, choice="approve"))

    assert result["success"] is True
    payload = result["result"]
    assert payload["routed_capability_id"] == "proposal.approval.execute"
    assert payload["approval_semantics_implemented_by_human_consultation"] is False
    assert payload["mutation_performed_by_human_interface"] is False
    assert ProposalService(tmp_path).get_proposal("PROP-HCONS-APPROVE").status == ProposalStatus.APPROVED
    assert service.get_request(consultation.consultation_id).status.value == "answered"


def test_adr_approval_consultation_routes_to_existing_adr_approval_capability(tmp_path: Path) -> None:
    adr_service = ArchitectureDecisionRecordService(tmp_path)
    adr = adr_service.propose_adr(
        project_id="Ageix",
        session_id="session-1",
        created_by="lex",
        title="Human consultation ADR approval",
        context="Context",
        decision="Decision",
        rationale="Rationale",
    )
    ProposalService(tmp_path).update_status(adr.proposal_id, ProposalStatus.APPROVED)
    proposal_before = ProposalService(tmp_path).get_proposal(adr.proposal_id).model_dump()
    service = HumanConsultationService(tmp_path)
    consultation = service.create_approval_request(
        project_id="Ageix",
        target_record_type="adr",
        target_record_id=adr.adr_id,
        question="Approve ADR?",
        summary="ADR approval requested.",
    )

    result = _execute(tmp_path, _chair_args(consultation.consultation_id, choice="approve"))

    assert result["success"] is True
    payload = result["result"]
    assert payload["routed_capability_id"] == "architecture.adr.approval.execute"
    assert adr_service.get_adr(adr.adr_id)["status"] == ArchitectureDecisionRecordStatus.ACCEPTED.value
    assert ProposalService(tmp_path).get_proposal(adr.proposal_id).model_dump() == proposal_before


def test_missing_evidence_consultation_can_be_answered_without_execution_logic(tmp_path: Path) -> None:
    service = HumanConsultationService(tmp_path)
    consultation = service.create_request(HumanConsultationRequest(
        project_id="Ageix",
        consultation_type=HumanConsultationType.MISSING_EVIDENCE,
        question="What evidence should be used?",
        summary="Missing evidence decision needed.",
        choices=missing_evidence_choices(),
    ))
    args = _chair_args(consultation.consultation_id, choice="provide_evidence")
    args["freeform_text"] = "Use EVPKG-123."

    result = service.respond(args)

    assert result["success"] is True
    assert result["result"]["routed_capability_id"] is None
    assert service.get_request(consultation.consultation_id).status.value == "answered"
