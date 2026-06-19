from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_session import AgentSession


class AgentSessionService:
    """Persists external-agent session context for capability requests."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "agent_sessions.json"

    def create_session(self, session_id: str, agent_id: str, project_id: str | None = None, metadata: dict[str, Any] | None = None) -> AgentSession:
        session = AgentSession(session_id=session_id, agent_id=agent_id, project_id=project_id, metadata=metadata or {})
        data = self._load()
        data.setdefault("sessions", {})[session_id] = session.model_dump()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        return session

    def get_session(self, session_id: str) -> AgentSession | None:
        raw = self._load().get("sessions", {}).get(session_id)
        return AgentSession(**raw) if raw else None

    def require_session(self, session_id: str) -> AgentSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Unknown session_id: {session_id}")
        return session

    def record_capability_use(self, session_id: str, agent_id: str, capability_id: str, project_id: str | None = None) -> AgentSession:
        session = self.get_session(session_id) or self.create_session(session_id, agent_id, project_id=project_id)
        if project_id and not session.project_id:
            session.project_id = project_id
        session.last_activity = datetime.now(timezone.utc).isoformat()
        session.updated_at = session.last_activity
        if capability_id not in session.capabilities_used:
            session.capabilities_used.append(capability_id)
        data = self._load()
        data.setdefault("sessions", {})[session_id] = session.model_dump()
        data["updated_at"] = session.last_activity
        self._write(data)
        return session

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            now = datetime.now(timezone.utc).isoformat()
            return {"schema_version": 1, "created_at": now, "updated_at": now, "sessions": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
