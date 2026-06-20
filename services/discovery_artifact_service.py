from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class DiscoveryArtifactService:
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)

    def run_dir(self, run_id: str) -> Path:
        return self.repo_root / ".ageix" / "runs" / run_id

    def persist_artifacts(self, *, run_id: str, artifacts: dict[str, Any]) -> Path:
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        for name, value in artifacts.items():
            path = run_dir / name
            path.write_text(json.dumps(self._jsonable(value), indent=2, sort_keys=True), encoding="utf-8")
        return run_dir

    def timestamp(self) -> str:
        return datetime.now(UTC).isoformat()

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        return value
