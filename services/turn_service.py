from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.conversation_policy import DIRECTED_QUESTION_RESPONSE_TYPES
from models.conversation_turn import ConversationTurn, TurnType
from services.participant_service import ParticipantService


class TurnService:
    """Appends and retrieves immutable, append-only conversation turns, per ADR-0016.

    Turns are never updated or deleted once committed; this service exposes no
    mutation path for existing turns, only append and read.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "conversation_turns.json"
        self.participants = ParticipantService(self.repo_root)

    def append_turn(
        self,
        conversation_id: str,
        *,
        speaker_client_id: str,
        speaker_agent_role: AgentRole | str,
        speaker_session_id: str,
        model_id: str,
        turn_type: TurnType | str,
        confidence: float,
        content: str,
        directed_at: str | None = None,
        participant_id: str | None = None,
    ) -> ConversationTurn:
        role = speaker_agent_role if isinstance(speaker_agent_role, AgentRole) else AgentRole.parse(speaker_agent_role)
        resolved_turn_type = turn_type if isinstance(turn_type, TurnType) else TurnType(str(turn_type))

        if resolved_turn_type is TurnType.DIRECTIVE and participant_id != "greg":
            raise ValueError("directive_turns_restricted_to_greg")

        pending = self.participants.pending_obligation_count_for_role(conversation_id, role)
        if pending and resolved_turn_type.value not in DIRECTED_QUESTION_RESPONSE_TYPES:
            raise ValueError("directed_question_response_contract_violated")

        existing = self._load_turns(conversation_id)
        turn = ConversationTurn(
            conversation_id=conversation_id,
            sequence_number=len(existing) + 1,
            speaker_client_id=speaker_client_id,
            speaker_agent_role=role,
            speaker_session_id=speaker_session_id,
            model_id=model_id,
            turn_type=resolved_turn_type,
            directed_at=directed_at,
            confidence=confidence,
            content=content,
        )

        data = self._load()
        data.setdefault("conversations", {}).setdefault(conversation_id, []).append(turn.model_dump())
        self._write(data)

        if resolved_turn_type is TurnType.QUESTION and directed_at and directed_at != "greg":
            self.participants.add_directed_obligation_for_role(conversation_id, agent_role=AgentRole.parse(directed_at), turn_id=turn.turn_id)
        if pending:
            self.participants.clear_obligations_for_role(conversation_id, agent_role=role)

        return turn

    def list_turns(self, conversation_id: str, *, limit: int | None = None, offset: int = 0, most_recent: bool = False) -> list[dict[str, Any]]:
        turns = self._load_turns(conversation_id)
        if most_recent and limit is not None:
            return turns[-limit:]
        if limit is None:
            return turns[offset:]
        return turns[offset:offset + limit]

    def _load_turns(self, conversation_id: str) -> list[dict[str, Any]]:
        return list(self._load().get("conversations", {}).get(conversation_id, []))

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "conversations": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
