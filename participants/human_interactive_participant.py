from __future__ import annotations

from typing import Any

from models.consultation_recommendation import ConsultationDisposition
from models.participant_response import ParticipantResponse
from participants.base import ConsultationParticipantBase
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService


class HumanInteractiveParticipant(ConsultationParticipantBase):
    """Participant adapter for responses collected through interactive turns."""

    def __init__(self, response: ParticipantResponse | None = None, participant_id: str = "human_interactive") -> None:
        super().__init__(participant_id)
        self.response = response

    def participate(self, session: dict[str, Any], broker: ConsultationEvidenceBrokerService) -> ParticipantResponse:
        if self.response is None:
            return ParticipantResponse(
                participant_id=self.participant_id,
                recommendation="Human interactive participant is awaiting input.",
                confidence=0.0,
                disposition=ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE,
                evidence_sufficient=False,
                findings=["Interactive prompt must be completed by a human or UI client."],
                metadata={"awaiting_human_input": True, "broker_required": broker is not None},
            )
        if self.response.participant_id != self.participant_id:
            raise ValueError("Human interactive response participant does not match the participant adapter.")
        return self.response
