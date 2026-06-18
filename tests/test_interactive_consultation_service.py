import json
from pathlib import Path

import pytest

from models.consultation import ConsultationType, EscalationDecision, EscalationDecisionAction
from models.evidence_request import EvidenceRequest
from models.participant_response import ParticipantResponse
from models.work_packet import WorkPacket
from services.consultation_api_service import ConsultationApiService
from services.consultation_orchestration_service import ConsultationOrchestrationService
from services.consultation_prompt_service import CliPromptRenderer
from services.consultation_proposal_service import ConsultationProposalService
from services.consultation_session_service import ConsultationSessionService


def _approved_session(tmp_path: Path):
    packet = WorkPacket(
        objective="Review interactive consultation",
        approved_scope=["services/foo.py", "tests/test_foo.py"],
        repository_evidence=["services/foo.py"],
        test_targets=["tests/test_foo.py"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["interactive_consultation_required"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )
    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)
    return ConsultationSessionService(tmp_path).create_session(
        proposal,
        approval={"approved_by": "human", "decision": "approve"},
    )


def test_interactive_turn_creates_ui_neutral_prompt(tmp_path: Path):
    session = _approved_session(tmp_path)

    prompt = ConsultationOrchestrationService(tmp_path).start_interactive_turn(session["consultation_id"])

    assert prompt.consultation_id == session["consultation_id"]
    assert prompt.turn_number == 1
    assert prompt.available_evidence
    assert "recommendation" in prompt.required_fields


def test_cli_renderer_includes_evidence_ids(tmp_path: Path):
    session = _approved_session(tmp_path)
    prompt = ConsultationOrchestrationService(tmp_path).start_interactive_turn(session["consultation_id"])

    rendered = CliPromptRenderer().render(prompt)

    assert "Consultation Session:" in rendered
    assert "EV-" in rendered


def test_submit_response_persists_turn_and_consultation_response(tmp_path: Path):
    session = _approved_session(tmp_path)
    svc = ConsultationOrchestrationService(tmp_path)
    svc.start_interactive_turn(session["consultation_id"])

    updated = svc.submit_participant_response(
        session["consultation_id"],
        ParticipantResponse(
            participant_id="human_interactive",
            recommendation="Keep consultation web-ready and brokered.",
            confidence=0.9,
            evidence_sufficient=True,
            findings=["No repository access was granted."],
        ),
    )

    assert updated["status"] == "confidence_satisfied"
    assert updated["turns"][0]["status"] == "confidence_satisfied"
    assert updated["consultation_responses"][0]["recommendation"] == "Keep consultation web-ready and brokered."


def test_followup_evidence_request_must_use_known_evidence_id(tmp_path: Path):
    session = _approved_session(tmp_path)
    svc = ConsultationOrchestrationService(tmp_path)
    svc.start_interactive_turn(session["consultation_id"])

    with pytest.raises(ValueError):
        svc.submit_participant_response(
            session["consultation_id"],
            ParticipantResponse(
                participant_id="human_interactive",
                recommendation="Need more evidence.",
                confidence=0.4,
                evidence_sufficient=False,
                requested_followup_evidence=[
                    EvidenceRequest(
                        request_id="REQ-001",
                        requested_evidence_id="services/foo.py",
                        reason="Attempt to bypass broker evidence IDs.",
                    )
                ],
            ),
        )


def test_followup_evidence_request_flows_through_broker(tmp_path: Path):
    session = _approved_session(tmp_path)
    svc = ConsultationOrchestrationService(tmp_path)
    prompt = svc.start_interactive_turn(session["consultation_id"])
    evidence_id = next(item["evidence_id"] for item in prompt.available_evidence if item.get("requestable", True))

    updated = svc.submit_participant_response(
        session["consultation_id"],
        ParticipantResponse(
            participant_id="human_interactive",
            recommendation="Need one evidence item before final decision.",
            confidence=0.5,
            evidence_sufficient=False,
            requested_followup_evidence=[
                EvidenceRequest(
                    request_id="REQ-001",
                    requested_evidence_id=evidence_id,
                    reason="Need brokered evidence for the current turn.",
                    round_number=1,
                )
            ],
        ),
    )

    assert updated["evidence_requests"][0]["requested_evidence_id"] == evidence_id
    assert updated["evidence_responses"][0]["requested_evidence_id"] == evidence_id


def test_max_interactive_turns_enforced(tmp_path: Path):
    config = tmp_path / ".ageix" / "config"
    config.mkdir(parents=True)
    (config / "controls.json").write_text(json.dumps({"consultation": {"max_interactive_turns": 1}}))
    session = _approved_session(tmp_path)
    svc = ConsultationOrchestrationService(tmp_path)

    svc.start_interactive_turn(session["consultation_id"])
    svc.submit_participant_response(
        session["consultation_id"],
        ParticipantResponse(
            participant_id="human_interactive",
            recommendation="More review needed.",
            confidence=0.5,
            evidence_sufficient=False,
        ),
    )

    with pytest.raises(PermissionError):
        svc.start_interactive_turn(session["consultation_id"])


def test_stub_participant_runs_without_repository_access(tmp_path: Path):
    session = _approved_session(tmp_path)

    updated = ConsultationOrchestrationService(tmp_path).run_stub_participant(session["consultation_id"])

    assert updated["status"] == "confidence_satisfied"
    assert updated["consultation_responses"][0]["participant_id"] == "stub_architect"


def test_consultation_api_boundary_returns_rendered_prompt(tmp_path: Path):
    session = _approved_session(tmp_path)

    payload = ConsultationApiService(tmp_path).get_pending_prompt(session["consultation_id"])

    assert payload["prompt"]["consultation_id"] == session["consultation_id"]
    assert "Consultation Session:" in payload["rendered_text"]


def test_consultation_api_boundary_accepts_structured_response(tmp_path: Path):
    session = _approved_session(tmp_path)
    api = ConsultationApiService(tmp_path)
    api.get_pending_prompt(session["consultation_id"])

    updated = api.submit_response(
        session["consultation_id"],
        {
            "participant_id": "human_interactive",
            "recommendation": "Proceed after preserving broker boundaries.",
            "confidence": 0.88,
            "evidence_sufficient": True,
        },
    )

    assert updated["status"] == "confidence_satisfied"
