from __future__ import annotations

from typing import Any

from models.consultation_recommendation import ConsultationDisposition
from models.participant_response import ParticipantResponse
from participants.base import ConsultationParticipantBase
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService


class StubArchitectureParticipant(ConsultationParticipantBase):
    """Deterministic architecture participant used to exercise orchestration."""

    def __init__(self, participant_id: str = "stub_architect") -> None:
        super().__init__(participant_id)

    def participate(self, session: dict[str, Any], broker: ConsultationEvidenceBrokerService) -> ParticipantResponse:
        return ParticipantResponse(
            participant_id=self.participant_id,
            recommendation="Repository appears properly scoped.",
            confidence=0.75,
            disposition=ConsultationDisposition.PROCEED,
            evidence_sufficient=True,
            findings=["Architecture participant reviewed brokered session metadata only."],
            metadata={"deterministic_stub": True, "broker_required": broker is not None},
        )
