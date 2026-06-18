from pathlib import Path

from models.consultation_participant import ConsultationParticipant
from services.participant_registry_service import ParticipantRegistryService


def test_participant_registry_lists_default_participants(tmp_path: Path):
    participants = ParticipantRegistryService(tmp_path).list_participants()

    ids = {participant.participant_id for participant in participants}

    assert "stub_architect" in ids
    assert "human_interactive" in ids


def test_participant_registry_registers_participant(tmp_path: Path):
    svc = ParticipantRegistryService(tmp_path)
    participant = ConsultationParticipant(
        participant_id="validation_specialist",
        participant_type="specialist",
        specialties=["validation"],
    )

    svc.register_participant(participant)

    assert svc.get_participant("validation_specialist").specialties == ["validation"]


def test_participant_registry_filters_by_specialty(tmp_path: Path):
    svc = ParticipantRegistryService(tmp_path)

    matches = svc.find_by_specialty("architecture")

    assert any(participant.participant_id == "stub_architect" for participant in matches)
