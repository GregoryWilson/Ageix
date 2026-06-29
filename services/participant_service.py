from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.conversation_participant import ConversationParticipant
from models.conversation_policy import CONFIDENCE_THRESHOLDS, confidence_threshold_for_role


class ParticipantService:
    """Tracks registered participants and directed-question obligations per conversation, per ADR-0016."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "conversation_participants.json"

    def register_participants(self, conversation_id: str, participants: list[dict[str, Any]]) -> list[ConversationParticipant]:
        data = self._load()
        bucket = self._conversation_bucket(data, conversation_id)
        now = datetime.now(timezone.utc).isoformat()
        registered = []
        for raw in participants:
            role = AgentRole.parse(raw.get("agent_role"))
            participant = ConversationParticipant(
                client_id=str(raw.get("client_id")),
                agent_role=role,
                session_id=str(raw.get("session_id")),
                confidence_threshold=confidence_threshold_for_role(role),
                joined_at=now,
            )
            bucket["participants"][self._key(participant.client_id, participant.agent_role, participant.session_id)] = participant.model_dump()
            registered.append(participant)
        self._write(data)
        return registered

    def list_participants(self, conversation_id: str) -> list[ConversationParticipant]:
        bucket = self._load().get("conversations", {}).get(conversation_id, {})
        return [ConversationParticipant(**raw) for raw in bucket.get("participants", {}).values()]

    def confidence_thresholds(self) -> dict[str, float]:
        return dict(CONFIDENCE_THRESHOLDS)

    def add_directed_obligation_for_role(self, conversation_id: str, *, agent_role: AgentRole, turn_id: str) -> None:
        data = self._load()
        bucket = self._conversation_bucket(data, conversation_id)
        obligations = bucket["obligations"].setdefault(agent_role.value, [])
        if turn_id not in obligations:
            obligations.append(turn_id)
        self._write(data)

    def clear_obligations_for_role(self, conversation_id: str, *, agent_role: AgentRole) -> None:
        data = self._load()
        bucket = self._conversation_bucket(data, conversation_id)
        bucket["obligations"][agent_role.value] = []
        self._write(data)

    def pending_obligation_count_for_role(self, conversation_id: str, agent_role: AgentRole) -> int:
        bucket = self._load().get("conversations", {}).get(conversation_id, {})
        return len(bucket.get("obligations", {}).get(agent_role.value, []))

    def pending_obligations(self, conversation_id: str) -> dict[str, list[str]]:
        bucket = self._load().get("conversations", {}).get(conversation_id, {})
        return dict(bucket.get("obligations", {}))

    @staticmethod
    def _key(client_id: str, agent_role: AgentRole, session_id: str) -> str:
        return f"{client_id}::{agent_role.value}::{session_id}"

    @staticmethod
    def _conversation_bucket(data: dict[str, Any], conversation_id: str) -> dict[str, Any]:
        bucket = data.setdefault("conversations", {}).setdefault(conversation_id, {})
        bucket.setdefault("participants", {})
        bucket.setdefault("obligations", {})
        return bucket

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "conversations": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
