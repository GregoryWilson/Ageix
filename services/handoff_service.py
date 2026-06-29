from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.handoff_package import HandoffPackage
from services.conversation_service import ConversationService
from services.turn_service import TurnService


class HandoffService:
    """Serializes and retrieves governed HANDOFF_PACKAGE artifacts for conversation handoff, per ADR-0016."""

    RECENT_TURN_COUNT = 10

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "conversation_handoffs.json"
        self.conversations = ConversationService(self.repo_root)
        self.turns = TurnService(self.repo_root)

    def create_handoff(
        self,
        conversation_id: str,
        *,
        requested_action: str,
        conversation_summary: str = "",
        outstanding_questions: list[dict[str, Any]] | None = None,
    ) -> HandoffPackage:
        conversation = self.conversations.require_conversation(conversation_id)
        recent_turns = self.turns.list_turns(conversation_id, limit=self.RECENT_TURN_COUNT, most_recent=True)
        package = HandoffPackage(
            conversation_id=conversation_id,
            participants=conversation.participants,
            rules_of_engagement=conversation.rules_of_engagement,
            conversation_summary=conversation_summary,
            outstanding_questions=outstanding_questions or [],
            conversation_state=conversation.state,
            recent_turns=recent_turns,
            requested_action=requested_action,
        )
        data = self._load()
        data.setdefault("handoffs", {})[package.handoff_id] = package.model_dump()
        self._write(data)
        return package

    def get_handoff(self, handoff_id: str) -> HandoffPackage | None:
        raw = self._load().get("handoffs", {}).get(handoff_id)
        return HandoffPackage(**raw) if raw else None

    def require_handoff(self, handoff_id: str) -> HandoffPackage:
        package = self.get_handoff(handoff_id)
        if package is None:
            raise ValueError(f"Unknown handoff_id: {handoff_id}")
        return package

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "handoffs": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
