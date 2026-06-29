from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.conversation_event import ConversationEvent


class ConversationEventService:
    """Records governance events alongside a conversation, distinct from turns, per ADR-0016."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "conversation_events.json"

    def record_event(
        self,
        conversation_id: str,
        *,
        event_type: str,
        governance_action_id: str,
        actor_agent_role: AgentRole | str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ConversationEvent:
        role = actor_agent_role if isinstance(actor_agent_role, AgentRole) else AgentRole.parse(actor_agent_role)
        event = ConversationEvent(
            conversation_id=conversation_id,
            event_type=event_type,
            governance_action_id=governance_action_id,
            actor_agent_role=role,
            description=description,
            metadata=metadata or {},
        )
        data = self._load()
        data.setdefault("conversations", {}).setdefault(conversation_id, []).append(event.model_dump())
        self._write(data)
        return event

    def list_events(self, conversation_id: str) -> list[dict[str, Any]]:
        return list(self._load().get("conversations", {}).get(conversation_id, []))

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "conversations": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
