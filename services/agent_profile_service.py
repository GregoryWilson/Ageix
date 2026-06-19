from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_profile import AgentProfile


class AgentProfileService:
    """Persists human-seeded external agent reputation profiles."""

    DEFAULT_BUDGETS = {
        "unknown": {"max_files": 2, "max_lines": 400, "max_items": 2},
        "trusted": {"max_files": 8, "max_lines": 2000, "max_items": 8},
        "strategic": {"max_files": 20, "max_lines": 8000, "max_items": 20},
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "agent_profiles.json"

    def get_profile(self, agent_id: str) -> AgentProfile:
        data = self._load()
        raw = data.get("agents", {}).get(agent_id)
        if raw:
            return AgentProfile(**raw)
        return AgentProfile(agent_id=agent_id)

    def list_profiles(self) -> list[AgentProfile]:
        data = self._load()
        return [AgentProfile(**raw) for raw in data.get("agents", {}).values()]

    def upsert_profile(self, profile: AgentProfile) -> AgentProfile:
        data = self._load()
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        data.setdefault("agents", {})[profile.agent_id] = profile.model_dump()
        self._write(data)
        return profile

    def evidence_budget(self, agent_id: str, controls: dict[str, Any] | None = None) -> dict[str, int]:
        profile = self.get_profile(agent_id)
        configured = (controls or {}).get("reputation_budgets", {}) if isinstance(controls, dict) else {}
        defaults = dict(self.DEFAULT_BUDGETS.get(profile.reputation_level, self.DEFAULT_BUDGETS["unknown"]))
        if isinstance(configured.get(profile.reputation_level), dict):
            defaults.update(configured[profile.reputation_level])
        return {key: int(value) for key, value in defaults.items()}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "agents": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
