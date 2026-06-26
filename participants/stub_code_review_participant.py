from __future__ import annotations

from typing import Any

from models.consultation_recommendation import ConsultationDisposition
from models.participant_response import ParticipantResponse
from participants.base import ConsultationParticipantBase
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService


class StubCodeReviewParticipant(ConsultationParticipantBase):
    """Deterministic code review participant used for multi-participant tests."""

    def __init__(self, participant_id: str = "stub_code_reviewer") -> None:
        super().__init__(participant_id)

    def participate(self, session: dict[str, Any], broker: ConsultationEvidenceBrokerService) -> ParticipantResponse:
        return ParticipantResponse(
            participant_id=self.participant_id,
            recommendation="No governance concerns identified.",
            confidence=0.70,
            disposition=ConsultationDisposition.PROCEED,
            evidence_sufficient=True,
            findings=["Code review participant did not receive direct repository access."],
            metadata={"deterministic_stub": True, "broker_required": broker is not None},
        )
