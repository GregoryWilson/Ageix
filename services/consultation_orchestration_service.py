from __future__ import annotations

from pathlib import Path
from typing import Any

from models.consultation_response import ConsultationResponse
from models.consultation_turn import ConsultationTurn
from models.evidence_request import EvidenceRequest
from models.interactive_prompt import InteractivePrompt
from models.participant_response import ParticipantResponse
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService
from services.consultation_prompt_service import build_available_evidence
from services.consultation_session_service import ConsultationSessionService
from services.controls_service import ControlsService
from services.participant_registry_service import ParticipantRegistryService


class ConsultationOrchestrationService:
    """Runs web-ready, turn-based consultation interactions.

    The orchestrator manages session state and brokered evidence. It does not
    perform console input or own UI behavior.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.session_service = ConsultationSessionService(self.repo_root)
        self.registry = ParticipantRegistryService(self.repo_root)
        self.broker = ConsultationEvidenceBrokerService(str(self.repo_root))
        self.controls = ControlsService(self.repo_root).get_raw_config().get("consultation", {})

    def start_interactive_turn(self, consultation_id: str, participant_id: str = "human_interactive") -> InteractivePrompt:
        session = self.session_service.load_session(consultation_id)
        participant = self.registry.get_participant(participant_id)
        if not participant.enabled:
            raise PermissionError("Consultation participant is disabled.")
        if session.get("status") not in {"approved", "waiting_for_participant", "waiting_for_evidence", "response_recorded"}:
            raise PermissionError("Consultation session is not ready for participant interaction.")

        turn_number = int(session.get("current_turn", 0)) + 1
        self._enforce_max_turns(turn_number)
        objective = (session.get("proposal") or {}).get("evidence_dictionary", {}).get("objective", "")
        if not objective:
            objective = (session.get("evidence_dictionary") or {}).get("objective", "")
        prompt = InteractivePrompt(
            consultation_id=consultation_id,
            turn_number=turn_number,
            participant_id=participant_id,
            title="Human consultation guidance requested" if participant.participant_type == "human_interactive" else "Consultation guidance requested",
            objective=objective,
            prompt_text="Review the brokered evidence metadata and provide a structured recommendation. Request follow-up evidence only by EV-* evidence ID.",
            available_evidence=build_available_evidence(session.get("evidence_dictionary") or {}),
            metadata={
                "participant_type": participant.participant_type,
                "minimum_evidence_confidence": self.minimum_evidence_confidence,
            },
        )
        turn = ConsultationTurn(
            turn_number=turn_number,
            participant_id=participant_id,
            status="waiting_for_input",
            prompt=prompt,
        )
        session.setdefault("turns", []).append(turn.model_dump())
        session["current_turn"] = turn_number
        session["status"] = "waiting_for_participant"
        self.session_service._persist_session(session)
        return prompt

    def submit_participant_response(self, consultation_id: str, response: ParticipantResponse) -> dict[str, Any]:
        session = self.session_service.load_session(consultation_id)
        if not session.get("turns"):
            raise ValueError("No active consultation turn exists for this session.")
        turn = session["turns"][-1]
        if turn.get("participant_id") != response.participant_id:
            raise ValueError("Participant response does not match the active turn participant.")

        response.metadata.setdefault("minimum_evidence_confidence", self.minimum_evidence_confidence)
        self._validate_followup_requests(session, response)
        for request in response.requested_followup_evidence:
            self.broker.serve_evidence(consultation_id, request)

        normalized = ConsultationResponse(
            participant_id=response.participant_id,
            participant_type="human" if response.participant_id.startswith("human") else "specialist",
            recommendation=response.recommendation,
            confidence=response.confidence,
            findings=response.findings,
            requested_followup_evidence=response.requested_followup_evidence,
            metadata=response.metadata,
        )
        updated = self.session_service.record_consultation_response(consultation_id, normalized)
        updated["turns"][-1]["status"] = "confidence_satisfied" if self._confidence_satisfied(response) else "response_recorded"
        updated["turns"][-1]["response"] = response.model_dump()
        updated["status"] = "confidence_satisfied" if self._confidence_satisfied(response) else "waiting_for_participant"
        if updated["status"] != "confidence_satisfied" and int(updated.get("current_turn", 1)) >= self.max_interactive_turns:
            updated["status"] = "blocked"
            updated["turns"][-1]["status"] = "max_turns_reached"
        self.session_service._persist_session(updated)
        return updated

    def run_stub_participant(self, consultation_id: str, participant_id: str = "stub_architect") -> dict[str, Any]:
        self.start_interactive_turn(consultation_id, participant_id)
        return self.submit_participant_response(
            consultation_id,
            ParticipantResponse(
                participant_id=participant_id,
                recommendation="Brokered evidence is available for governed consultation orchestration.",
                confidence=max(self.minimum_evidence_confidence, 0.75),
                evidence_sufficient=True,
                findings=["Participant orchestration executed without repository access."],
                metadata={"deterministic_stub": True, "minimum_evidence_confidence": self.minimum_evidence_confidence},
            ),
        )

    @property
    def minimum_evidence_confidence(self) -> float:
        return float(self.controls.get("minimum_evidence_confidence", 0.85))

    @property
    def max_interactive_turns(self) -> int:
        return int(self.controls.get("max_interactive_turns", 5))

    def _confidence_satisfied(self, response: ParticipantResponse) -> bool:
        return response.evidence_sufficient and response.confidence >= self.minimum_evidence_confidence

    def _enforce_max_turns(self, turn_number: int) -> None:
        if turn_number > self.max_interactive_turns:
            raise PermissionError("Consultation exceeded the maximum interactive turn count.")

    def _validate_followup_requests(self, session: dict[str, Any], response: ParticipantResponse) -> None:
        known_ids = {
            item.get("evidence_id")
            for item in (session.get("evidence_dictionary") or {}).get("items", [])
        }
        for index, request in enumerate(response.requested_followup_evidence, start=1):
            if request.requested_evidence_id not in known_ids:
                raise ValueError("Follow-up evidence requests must reference known EV-* evidence IDs.")
            if request.participant_id is None:
                request.participant_id = response.participant_id
            if request.round_number < 1:
                request.round_number = int(session.get("current_turn", 1))
            if not request.request_id:
                request.request_id = f"REQ-{int(session.get('current_turn', 1)):03d}-{index:03d}"
