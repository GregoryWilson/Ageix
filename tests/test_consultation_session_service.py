from pathlib import Path

from models.consultation import ConsultationType, EscalationDecision, EscalationDecisionAction
from models.consultation_response import ConsultationResponse
from models.evidence_request import EvidenceRequest
from models.work_packet import WorkPacket
from services.consultation_proposal_service import ConsultationProposalService
from services.consultation_session_service import ConsultationSessionService


def _proposal(tmp_path: Path):
    packet = WorkPacket(
        objective="Review consultation sessions",
        approved_scope=["services/foo.py"],
        repository_evidence=["services/foo.py"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["high_context_complexity"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )
    return ConsultationProposalService(tmp_path).build_proposal(packet, decision)


def test_create_consultation_session(tmp_path: Path):
    proposal = _proposal(tmp_path)

    session = ConsultationSessionService(tmp_path).create_session(proposal)

    assert session["consultation_id"].startswith("ARCH-")
    assert session["proposal"]["consultation_type"] == "architecture_review"
    assert session["evidence_dictionary"]["items"]


def test_consultation_session_persistence(tmp_path: Path):
    proposal = _proposal(tmp_path)
    svc = ConsultationSessionService(tmp_path)

    session = svc.create_session(proposal, approval={"approved_by": "human", "decision": "approve"})
    loaded = svc.load_session(session["consultation_id"])

    assert loaded["status"] == "approved"
    assert loaded["approval"]["approved_by"] == "human"
    assert (tmp_path / ".ageix" / "manifests" / "consultations" / session["consultation_id"] / "session.json").exists()


def test_consultation_session_tracks_token_usage(tmp_path: Path):
    proposal = _proposal(tmp_path)

    session = ConsultationSessionService(tmp_path).create_session(proposal)

    assert session["token_usage"]["estimated_total_tokens"] == proposal.token_estimate.estimated_total_tokens
    assert session["token_usage"]["served_evidence_tokens"] == 0


def test_session_persists_evidence_requests(tmp_path: Path):
    proposal = _proposal(tmp_path)
    svc = ConsultationSessionService(tmp_path)
    session = svc.create_session(proposal)
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repository summary")

    svc.record_evidence_request(session["consultation_id"], request)
    loaded = svc.load_session(session["consultation_id"])

    assert loaded["evidence_requests"][0]["request_id"] == "REQ-001"


def test_session_persists_consultation_responses(tmp_path: Path):
    proposal = _proposal(tmp_path)
    svc = ConsultationSessionService(tmp_path)
    session = svc.create_session(proposal)
    response = ConsultationResponse(
        participant_id="architect_consultant",
        recommendation="Proceed with brokered evidence only.",
        confidence=0.82,
    )

    svc.record_consultation_response(session["consultation_id"], response)
    loaded = svc.load_session(session["consultation_id"])

    assert loaded["consultation_responses"][0]["participant_id"] == "architect_consultant"
