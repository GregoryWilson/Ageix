from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.conversation import Conversation, ConversationState
from models.conversation_policy import CONFIDENCE_THRESHOLDS, DIRECTED_QUESTION_RESPONSE_TYPES, TURN_LIMIT_PER_THREAD
from models.conversation_turn import TurnType
from services.participant_service import ParticipantService
from services.turn_service import TurnService

ALLOWED_STATE_TRANSITIONS: dict[ConversationState, set[ConversationState]] = {
    ConversationState.OPEN: {ConversationState.ACTIVE, ConversationState.CLOSED},
    ConversationState.ACTIVE: {
        ConversationState.WAITING_FOR_GREG,
        ConversationState.WAITING_FOR_AGENT,
        ConversationState.CONVERGED,
        ConversationState.ESCALATED,
        ConversationState.CLOSED,
    },
    ConversationState.WAITING_FOR_GREG: {ConversationState.ACTIVE, ConversationState.ESCALATED, ConversationState.CLOSED},
    ConversationState.WAITING_FOR_AGENT: {ConversationState.ACTIVE, ConversationState.CLOSED},
    ConversationState.CONVERGED: {ConversationState.ACTIVE, ConversationState.CLOSED},
    ConversationState.ESCALATED: {ConversationState.ACTIVE, ConversationState.CLOSED},
    ConversationState.CLOSED: {ConversationState.ARCHIVED},
    ConversationState.ARCHIVED: set(),
}


class ConversationService:
    """Opens, transitions, and retrieves governed shared conversations, per ADR-0016."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "conversations.json"
        self.participants = ParticipantService(self.repo_root)
        self.turns = TurnService(self.repo_root)

    def open_conversation(
        self,
        participants: list[dict[str, Any]],
        *,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        conversation = Conversation(project_id=project_id, participants=participants, metadata=metadata or {})
        conversation.rules_of_engagement = self._build_rules_of_engagement(conversation.conversation_id, participants)
        self._save(conversation)
        self.participants.register_participants(conversation.conversation_id, participants)
        return conversation

    def transition_state(self, conversation_id: str, new_state: ConversationState | str) -> Conversation:
        conversation = self.require_conversation(conversation_id)
        target = new_state if isinstance(new_state, ConversationState) else ConversationState(str(new_state))
        if target not in ALLOWED_STATE_TRANSITIONS.get(conversation.state, set()):
            raise ValueError(f"invalid_conversation_state_transition_{conversation.state.value}_to_{target.value}")
        conversation.state = target
        conversation.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(conversation)
        return conversation

    def close_conversation(self, conversation_id: str) -> Conversation:
        return self.transition_state(conversation_id, ConversationState.CLOSED)

    def archive_conversation(self, conversation_id: str) -> Conversation:
        return self.transition_state(conversation_id, ConversationState.ARCHIVED)

    def get_conversation(self, conversation_id: str, *, recent_turn_limit: int = 10) -> dict[str, Any]:
        conversation = self.require_conversation(conversation_id)
        recent_turns = self.turns.list_turns(conversation_id, limit=recent_turn_limit, most_recent=True)
        return {
            "conversation_id": conversation.conversation_id,
            "project_id": conversation.project_id,
            "state": conversation.state.value,
            "participants": conversation.participants,
            "rules_of_engagement": conversation.rules_of_engagement,
            "recent_turns": recent_turns,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

    def get_conversation_record(self, conversation_id: str) -> Conversation | None:
        raw = self._load().get("conversations", {}).get(conversation_id)
        return Conversation(**raw) if raw else None

    def require_conversation(self, conversation_id: str) -> Conversation:
        conversation = self.get_conversation_record(conversation_id)
        if conversation is None:
            raise ValueError(f"Unknown conversation_id: {conversation_id}")
        return conversation

    @staticmethod
    def _build_rules_of_engagement(conversation_id: str, participants: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "version": "1.0",
            "conversation_id": conversation_id,
            "participants": participants,
            "turn_limit_per_thread": TURN_LIMIT_PER_THREAD,
            "confidence_thresholds": dict(CONFIDENCE_THRESHOLDS),
            "turn_types": [turn_type.value for turn_type in TurnType],
            "directed_question_contract": list(DIRECTED_QUESTION_RESPONSE_TYPES),
            "no_comment_on_directed_question": False,
            "proposals_by_reference_only": True,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "conversations": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, conversation: Conversation) -> None:
        data = self._load()
        data.setdefault("conversations", {})[conversation.conversation_id] = conversation.model_dump()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
