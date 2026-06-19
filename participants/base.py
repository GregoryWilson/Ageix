from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from models.participant_response import ParticipantResponse
from services.consultation_evidence_broker_service import ConsultationEvidenceBrokerService


class ConsultationParticipantBase(ABC):
    """Provider-independent execution contract for consultation participants.

    Participants receive only session state and the Evidence Broker. They must not
    receive repository paths, discovered files, or direct repository handles.
    """

    participant_id: str

    def __init__(self, participant_id: str) -> None:
        self.participant_id = participant_id

    @abstractmethod
    def participate(
        self,
        session: dict[str, Any],
        broker: ConsultationEvidenceBrokerService,
    ) -> ParticipantResponse:
        raise NotImplementedError
