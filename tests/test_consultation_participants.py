from pathlib import Path

import pytest

from models.consultation import ConsultationType, EscalationDecision, EscalationDecisionAction
from models.consultation_recommendation import ConsultationDisposition
from models.evidence_request import EvidenceRequest
from models.participant_response import ParticipantResponse
from models.work_packet import WorkPacket
from participants.human_interactive_participant import HumanInteractiveParticipant
from participants.stub_architecture_participant import StubArchitectureParticipant
from participants.stub_code_review_participant import StubCodeReviewParticipant
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService
from services.consultation_orchestration_service import ConsultationOrchestrationService
from services.consultation_proposal_service import ConsultationProposalService
from services.consultation_session_service import ConsultationSessionService


def _approved_session(tmp_path: Path):
    packet = WorkPacket(
        objective="Review participant execution",
        approved_scope=["services/foo.py", "tests/test_foo.py"],
        repository_evidence=["services/foo.py"],
        test_targets=["tests/test_foo.py"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["participant_execution_required"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )
    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)
    return ConsultationSessionService(tmp_path).create_session(
        proposal,
        approval={"approved_by": "human", "decision": "approve"},
    )


def test_human_interactive_participant():
    response = ParticipantResponse(
        participant_id="human_interactive",
        recommendation="Proceed with brokered consultation.",
        confidence=0.9,
        disposition=ConsultationDisposition.PROCEED,
        evidence_sufficient=True,
    )

    produced = HumanInteractiveParticipant(response=response).participate({}, object())

    assert produced.recommendation == "Proceed with brokered consultation."
    assert produced.disposition == ConsultationDisposition.PROCEED


def test_stub_architecture_participant():
    response = StubArchitectureParticipant().participate({}, object())

    assert response.participant_id == "stub_architect"
    assert response.recommendation == "Repository appears properly scoped."
    assert response.confidence == 0.75
    assert response.disposition == ConsultationDisposition.PROCEED


def test_stub_code_review_participant():
    response = StubCodeReviewParticipant().participate({}, object())

    assert response.participant_id == "stub_code_reviewer"
    assert response.recommendation == "No governance concerns identified."
    assert response.confidence == 0.70
    assert response.disposition == ConsultationDisposition.PROCEED


def test_orchestrator_executes_multiple_participants(tmp_path: Path):
    session = _approved_session(tmp_path)

    updated = ConsultationOrchestrationService(tmp_path).execute_participants(
        session["consultation_id"],
        ["stub_architect", "stub_code_reviewer"],
    )

    assert len(updated["consultation_responses"]) == 2
    assert updated["consultation_recommendation"]["participant_count"] == 2


def test_orchestrator_collects_responses(tmp_path: Path):
    session = _approved_session(tmp_path)

    updated = ConsultationOrchestrationService(tmp_path).execute_participants(
        session["consultation_id"],
        ["stub_architect", "stub_code_reviewer"],
    )

    ids = {item["participant_id"] for item in updated["consultation_responses"]}
    assert ids == {"stub_architect", "stub_code_reviewer"}


def test_orchestrator_produces_recommendation(tmp_path: Path):
    session = _approved_session(tmp_path)

    updated = ConsultationOrchestrationService(tmp_path).execute_participants(
        session["consultation_id"],
        ["stub_architect", "stub_code_reviewer"],
    )

    recommendation = updated["consultation_recommendation"]
    assert recommendation["consensus"] == "proceed"
    assert recommendation["aggregate_confidence"] >= 0.85


def test_participant_cannot_bypass_broker(tmp_path: Path):
    session = _approved_session(tmp_path)
    svc = ConsultationOrchestrationService(tmp_path)
    svc.start_interactive_turn(session["consultation_id"])

    with pytest.raises(ValueError):
        svc.submit_participant_response(
            session["consultation_id"],
            ParticipantResponse(
                participant_id="human_interactive",
                recommendation="Attempt direct path request.",
                confidence=0.2,
                evidence_sufficient=False,
                requested_followup_evidence=[
                    EvidenceRequest(
                        request_id="REQ-001",
                        requested_evidence_id="services/foo.py",
                        reason="Direct paths are not broker evidence IDs.",
                    )
                ],
            ),
        )


def test_participant_cannot_expand_scope(tmp_path: Path):
    session = _approved_session(tmp_path)
    session["evidence_dictionary"]["items"].append({
        "evidence_id": "EV-999",
        "evidence_type": "repository_path",
        "summary": "Unapproved path",
        "estimated_tokens": 1,
        "paths": ["services/out_of_scope.py"],
        "payload": ["services/out_of_scope.py"],
        "requestable": True,
    })
    ConsultationSessionService(tmp_path)._persist_session(session)

    with pytest.raises(PermissionError):
        ConsultationEvidenceBrokerService(tmp_path).serve_evidence(
            session["consultation_id"],
            EvidenceRequest(
                request_id="REQ-001",
                requested_evidence_id="EV-999",
                reason="Attempt scope expansion.",
            ),
        )
