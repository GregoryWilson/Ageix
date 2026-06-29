from __future__ import annotations

from pathlib import Path

import pytest

from models.conversation import ConversationState
from models.conversation_turn import TurnType
from services.conversation_service import ConversationService
from services.handoff_service import HandoffService
from services.participant_service import ParticipantService
from services.turn_service import TurnService

PARTICIPANTS = [
    {"client_id": "ageix-connector-claude-ai", "agent_role": "claude.ai", "session_id": "sess-architect"},
    {"client_id": "ageix-connector-claude-code", "agent_role": "claude.code", "session_id": "sess-worker"},
    {"client_id": "ageix-connector-chatgpt", "agent_role": "lex", "session_id": "sess-lex"},
]


def test_open_conversation_delivers_rules_of_engagement(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")

    assert conversation.state is ConversationState.OPEN
    roe = conversation.rules_of_engagement
    assert roe["turn_limit_per_thread"] == 6
    assert roe["confidence_thresholds"] == {"architect": 4.0, "worker": 6.0, "governance": 7.0}
    assert roe["directed_question_contract"] == ["ANSWER", "QUESTION", "ABSTAIN", "ESCALATE"]
    assert roe["no_comment_on_directed_question"] is False
    assert roe["proposals_by_reference_only"] is True
    assert set(roe["turn_types"]) == {t.value for t in TurnType}


def test_open_conversation_registers_participants(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")

    registered = ParticipantService(tmp_path).list_participants(conversation.conversation_id)
    roles = {p.agent_role.value for p in registered}
    assert roles == {"claude.ai", "claude.code", "lex"}
    thresholds = {p.agent_role.value: p.confidence_threshold for p in registered}
    assert thresholds == {"claude.ai": 4.0, "claude.code": 6.0, "lex": 4.0}


def test_transition_state_enforces_allowed_transitions(tmp_path: Path):
    service = ConversationService(tmp_path)
    conversation = service.open_conversation(PARTICIPANTS, project_id="Ageix")

    active = service.transition_state(conversation.conversation_id, ConversationState.ACTIVE)
    assert active.state is ConversationState.ACTIVE

    with pytest.raises(ValueError):
        service.transition_state(conversation.conversation_id, ConversationState.ARCHIVED)

    closed = service.close_conversation(conversation.conversation_id)
    assert closed.state is ConversationState.CLOSED
    archived = service.archive_conversation(conversation.conversation_id)
    assert archived.state is ConversationState.ARCHIVED

    with pytest.raises(ValueError):
        service.transition_state(conversation.conversation_id, ConversationState.ACTIVE)


def test_turn_append_assigns_sequence_numbers(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")
    turns = TurnService(tmp_path)

    first = turns.append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-ai",
        speaker_agent_role="claude.ai",
        speaker_session_id="sess-architect",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.STATEMENT,
        confidence=8.0,
        content="Proposing we proceed with PROP-E4539A0CF13D.",
    )
    second = turns.append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-code",
        speaker_agent_role="claude.code",
        speaker_session_id="sess-worker",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.OBSERVATION,
        confidence=7.0,
        content="Tests pass locally.",
    )

    assert first.sequence_number == 1
    assert second.sequence_number == 2
    history = turns.list_turns(conversation.conversation_id)
    assert [t["sequence_number"] for t in history] == [1, 2]


def test_directed_question_response_contract_enforced(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")
    turns = TurnService(tmp_path)

    turns.append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-ai",
        speaker_agent_role="claude.ai",
        speaker_session_id="sess-architect",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.QUESTION,
        directed_at="claude.code",
        confidence=8.0,
        content="Have you validated the migration against staging?",
    )

    with pytest.raises(ValueError):
        turns.append_turn(
            conversation.conversation_id,
            speaker_client_id="ageix-connector-claude-code",
            speaker_agent_role="claude.code",
            speaker_session_id="sess-worker",
            model_id="claude-sonnet-4-6",
            turn_type=TurnType.NO_COMMENT,
            confidence=5.0,
            content="N/A",
        )

    answer = turns.append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-code",
        speaker_agent_role="claude.code",
        speaker_session_id="sess-worker",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.ANSWER,
        confidence=7.0,
        content="Yes, validated against staging.",
    )
    assert answer.turn_type is TurnType.ANSWER

    cleared = turns.append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-code",
        speaker_agent_role="claude.code",
        speaker_session_id="sess-worker",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.NO_COMMENT,
        confidence=5.0,
        content="Nothing further.",
    )
    assert cleared.turn_type is TurnType.NO_COMMENT


def test_directive_restricted_to_greg(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")
    turns = TurnService(tmp_path)

    with pytest.raises(ValueError):
        turns.append_turn(
            conversation.conversation_id,
            speaker_client_id="ageix-connector-claude-ai",
            speaker_agent_role="claude.ai",
            speaker_session_id="sess-architect",
            model_id="claude-sonnet-4-6",
            turn_type=TurnType.DIRECTIVE,
            confidence=9.0,
            content="Proceed now.",
        )

    directive = turns.append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-ai",
        speaker_agent_role="claude.ai",
        speaker_session_id="sess-architect",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.DIRECTIVE,
        confidence=9.0,
        content="Proceed now (Greg override).",
        participant_id="greg",
    )
    assert directive.turn_type is TurnType.DIRECTIVE


def test_get_conversation_returns_summary_first_view(tmp_path: Path):
    service = ConversationService(tmp_path)
    conversation = service.open_conversation(PARTICIPANTS, project_id="Ageix")
    TurnService(tmp_path).append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-ai",
        speaker_agent_role="claude.ai",
        speaker_session_id="sess-architect",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.STATEMENT,
        confidence=8.0,
        content="Kickoff statement.",
    )

    summary = service.get_conversation(conversation.conversation_id)
    assert summary["state"] == "OPEN"
    assert len(summary["participants"]) == 3
    assert len(summary["recent_turns"]) == 1
    assert "rules_of_engagement" in summary


def test_handoff_package_creation_and_retrieval(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")
    TurnService(tmp_path).append_turn(
        conversation.conversation_id,
        speaker_client_id="ageix-connector-claude-ai",
        speaker_agent_role="claude.ai",
        speaker_session_id="sess-architect",
        model_id="claude-sonnet-4-6",
        turn_type=TurnType.STATEMENT,
        confidence=8.0,
        content="Kickoff statement.",
    )

    handoff_service = HandoffService(tmp_path)
    package = handoff_service.create_handoff(
        conversation.conversation_id,
        requested_action="Review and respond to outstanding questions.",
        conversation_summary="Sprint kickoff discussion.",
        outstanding_questions=[{"turn_id": "TURN-X", "question": "Pending?"}],
    )

    fetched = handoff_service.get_handoff(package.handoff_id)
    assert fetched is not None
    assert fetched.conversation_id == conversation.conversation_id
    assert fetched.conversation_state is ConversationState.OPEN
    assert len(fetched.recent_turns) == 1
    assert fetched.requested_action == "Review and respond to outstanding questions."


def test_handoff_requires_known_conversation(tmp_path: Path):
    with pytest.raises(ValueError):
        HandoffService(tmp_path).create_handoff("CONV-UNKNOWN", requested_action="Review.")
