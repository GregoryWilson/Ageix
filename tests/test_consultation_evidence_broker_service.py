import json
from pathlib import Path

import pytest

from models.consultation import ConsultationType, EscalationDecision, EscalationDecisionAction
from models.evidence_request import EvidenceRequest
from models.work_packet import WorkPacket
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService
from services.consultation_proposal_service import ConsultationProposalService
from services.consultation_session_service import ConsultationSessionService


def _write_controls(tmp_path: Path, consultation: dict):
    path = tmp_path / ".ageix" / "config"
    path.mkdir(parents=True, exist_ok=True)
    (path / "controls.json").write_text(json.dumps({"consultation": consultation}), encoding="utf-8")


def _approved_session(tmp_path: Path, packet: WorkPacket):
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["high_context_complexity"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )
    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)
    return ConsultationSessionService(tmp_path).create_session(
        proposal,
        approval={"approved_by": "human", "decision": "approve_cloud_consultation"},
    )


def test_broker_serves_known_evidence(tmp_path: Path):
    session = _approved_session(tmp_path, WorkPacket(
        objective="Review broker",
        approved_scope=["services/foo.py"],
        repository_evidence=["services/foo.py"],
    ))
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repo evidence")

    response = ConsultationEvidenceBrokerService(tmp_path).serve_evidence(session["consultation_id"], request)

    assert response["status"] == "served"
    assert response["evidence_id"] == "EV-002"
    assert response["payload"] == ["services/foo.py"]


def test_broker_rejects_unknown_evidence(tmp_path: Path):
    session = _approved_session(tmp_path, WorkPacket(objective="Review broker", approved_scope=["services/foo.py"]))
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-999", reason="Need unknown evidence")

    with pytest.raises(ValueError):
        ConsultationEvidenceBrokerService(tmp_path).serve_evidence(session["consultation_id"], request)


def test_broker_rejects_unapproved_scope(tmp_path: Path):
    session = _approved_session(tmp_path, WorkPacket(
        objective="Review broker",
        approved_scope=["services/foo.py"],
        repository_evidence=["services/bar.py"],
    ))
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repo evidence")

    with pytest.raises(PermissionError):
        ConsultationEvidenceBrokerService(tmp_path).serve_evidence(session["consultation_id"], request)


def test_broker_enforces_request_limits(tmp_path: Path):
    _write_controls(tmp_path, {"max_evidence_requests_per_round": 1})
    session = _approved_session(tmp_path, WorkPacket(
        objective="Review broker",
        approved_scope=["services/foo.py", "tests/test_foo.py"],
        repository_evidence=["services/foo.py"],
        test_targets=["tests/test_foo.py"],
    ))
    broker = ConsultationEvidenceBrokerService(tmp_path)
    broker.serve_evidence(session["consultation_id"], EvidenceRequest(
        request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repo evidence"
    ))

    with pytest.raises(PermissionError):
        broker.serve_evidence(session["consultation_id"], EvidenceRequest(
            request_id="REQ-002", requested_evidence_id="EV-006", reason="Need test target evidence"
        ))


def test_broker_enforces_token_limits(tmp_path: Path):
    _write_controls(tmp_path, {"max_evidence_tokens_per_request": 1})
    session = _approved_session(tmp_path, WorkPacket(
        objective="Review broker",
        approved_scope=["services/foo.py"],
        repository_evidence=["services/foo.py"],
    ))
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repo evidence")

    with pytest.raises(PermissionError):
        ConsultationEvidenceBrokerService(tmp_path).serve_evidence(session["consultation_id"], request)


def test_broker_cannot_expand_scope(tmp_path: Path):
    session = _approved_session(tmp_path, WorkPacket(
        objective="Review broker",
        approved_scope=["services/foo.py"],
        repository_evidence=["services/foo.py"],
    ))
    session["proposal"]["governance"]["cloud_may_expand_scope"] = True
    ConsultationSessionService(tmp_path)._persist_session(session)
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repo evidence")

    with pytest.raises(PermissionError):
        ConsultationEvidenceBrokerService(tmp_path).serve_evidence(session["consultation_id"], request)


def test_broker_cannot_request_unresolved_targets(tmp_path: Path):
    session = _approved_session(tmp_path, WorkPacket(
        objective="Review broker",
        approved_scope=["services/foo.py"],
        repository_evidence=["services/foo.py"],
    ))
    session["proposal"]["governance"]["repository_grounded"] = False
    ConsultationSessionService(tmp_path)._persist_session(session)
    request = EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="Need repo evidence")

    with pytest.raises(PermissionError):
        ConsultationEvidenceBrokerService(tmp_path).serve_evidence(session["consultation_id"], request)
