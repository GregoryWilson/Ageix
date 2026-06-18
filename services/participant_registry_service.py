from __future__ import annotations

import json
from pathlib import Path

from models.consultation_participant import ConsultationParticipant


class ParticipantRegistryService:
    """Config-backed registry for consultation participants."""

    DEFAULT_PARTICIPANTS = [
        ConsultationParticipant(
            participant_id="stub_architect",
            participant_type="stub",
            specialties=["architecture", "repository_design"],
            enabled=True,
        ),
        ConsultationParticipant(
            participant_id="human_interactive",
            participant_type="human_interactive",
            specialties=["architecture", "planning", "validation", "implementation"],
            enabled=True,
        ),
    ]

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry_path = self.repo_root / ".ageix" / "config" / "participants.json"

    def list_participants(self, *, enabled_only: bool = True) -> list[ConsultationParticipant]:
        participants = self._load_participants()
        if enabled_only:
            return [participant for participant in participants if participant.enabled]
        return participants

    def get_participant(self, participant_id: str) -> ConsultationParticipant:
        for participant in self.list_participants(enabled_only=False):
            if participant.participant_id == participant_id:
                return participant
        raise ValueError(f"Unknown consultation participant: {participant_id}")

    def find_by_specialty(self, specialty: str, *, enabled_only: bool = True) -> list[ConsultationParticipant]:
        needle = specialty.lower()
        return [
            participant
            for participant in self.list_participants(enabled_only=enabled_only)
            if needle in {item.lower() for item in participant.specialties}
        ]

    def register_participant(self, participant: ConsultationParticipant) -> ConsultationParticipant:
        participants = self.list_participants(enabled_only=False)
        filtered = [existing for existing in participants if existing.participant_id != participant.participant_id]
        filtered.append(participant)
        self._persist_participants(filtered)
        return participant

    def _load_participants(self) -> list[ConsultationParticipant]:
        if not self.registry_path.exists():
            return list(self.DEFAULT_PARTICIPANTS)
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        raw_participants = payload.get("participants", payload if isinstance(payload, list) else [])
        return [ConsultationParticipant(**item) for item in raw_participants]

    def _persist_participants(self, participants: list[ConsultationParticipant]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"participants": [participant.model_dump() for participant in participants]}
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
