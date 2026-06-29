from __future__ import annotations

from pathlib import Path
from typing import Any

import chair
from models.conversation_turn import TurnType
from services.agent_session_service import AgentSessionService
from services.conversation_event_service import ConversationEventService
from services.conversation_service import ConversationService

PARTICIPANTS = [
    {"client_id": "ageix-connector-claude-ai", "agent_role": "claude.ai", "session_id": "sess-architect"},
    {"client_id": "ageix-connector-claude-code", "agent_role": "claude.code", "session_id": "sess-worker"},
]


def test_provision_chair_session_identity_creates_session(tmp_path: Path):
    identity = chair.provision_chair_session_identity(tmp_path)

    assert identity == {
        "client_id": "ageix-chair",
        "agent_role": "ageix.chair",
        "session_id": "ageix-chair-session",
    }
    session = AgentSessionService(tmp_path).require_session("ageix-chair-session")
    assert session.agent_id == "chair"


def test_provision_chair_session_identity_is_idempotent(tmp_path: Path):
    first = chair.provision_chair_session_identity(tmp_path)
    second = chair.provision_chair_session_identity(tmp_path)

    assert first == second
    assert len(AgentSessionService(tmp_path)._load()["sessions"]) == 1


def test_conversation_context_evaluation_calls_qwen3_via_dispatch_agent(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_dispatch(agent_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured["agent_key"] = agent_key
        captured["payload"] = payload
        return {
            "agent": "conversation_evaluator",
            "conversation_summary": "Discussing migration approach.",
            "deadlock_confidence": 0.2,
            "disagreement_summary": "",
            "confidence": 8.0,
        }

    monkeypatch.setattr(chair, "dispatch_agent", fake_dispatch)

    result = chair.conversation_context_evaluation([{"content": "Proposing approach A."}])

    assert captured["agent_key"] == "conversation_evaluator"
    assert result["deadlock_confidence"] == 0.2


def test_escalate_if_deadlocked_posts_escalate_turn_when_above_threshold(tmp_path: Path, monkeypatch):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")

    def fake_dispatch(agent_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "conversation_summary": "Stuck in disagreement.",
            "deadlock_confidence": 0.9,
            "disagreement_summary": "Architect and worker disagree on rollout order.",
            "confidence": 7.5,
        }

    monkeypatch.setattr(chair, "dispatch_agent", fake_dispatch)

    posted = chair.escalate_if_deadlocked(conversation.conversation_id, [{"content": "..."}], tmp_path)

    assert posted is not None
    assert posted["turn_type"] == TurnType.ESCALATE.value
    assert posted["directed_at"] == "greg"
    assert posted["speaker_agent_role"] == "ageix.chair"
    assert posted["content"] == "Architect and worker disagree on rollout order."


def test_escalate_if_deadlocked_does_nothing_below_threshold(tmp_path: Path, monkeypatch):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")

    def fake_dispatch(agent_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"conversation_summary": "All good.", "deadlock_confidence": 0.1, "disagreement_summary": "", "confidence": 8.0}

    monkeypatch.setattr(chair, "dispatch_agent", fake_dispatch)

    posted = chair.escalate_if_deadlocked(conversation.conversation_id, [{"content": "..."}], tmp_path)

    assert posted is None


def test_record_chair_governance_action_creates_event_not_turn(tmp_path: Path):
    conversation = ConversationService(tmp_path).open_conversation(PARTICIPANTS, project_id="Ageix")

    event = chair.record_chair_governance_action(
        conversation.conversation_id,
        governance_action_id="GOV-ABC123",
        description="Approved proposal PROP-E4539A0CF13D.",
        repo_root=tmp_path,
    )

    assert event["governance_action_id"] == "GOV-ABC123"
    assert event["actor_agent_role"] == "ageix.chair"

    events = ConversationEventService(tmp_path).list_events(conversation.conversation_id)
    assert len(events) == 1
    assert events[0]["event_id"] == event["event_id"]

    turns = ConversationService(tmp_path).turns.list_turns(conversation.conversation_id)
    assert turns == []
