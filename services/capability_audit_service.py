from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.capability_audit_record import CapabilityAuditRecord


class CapabilityAuditService:
    """Append-only audit log for external agent capability calls."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "instance" / "capability_audit.json"

    def record(self, record: CapabilityAuditRecord) -> CapabilityAuditRecord:
        data = self._load()
        data.setdefault("records", []).append(record.model_dump())
        self._write(data)
        return record

    def list_records(self) -> list[dict[str, Any]]:
        return list(self._load().get("records", []))

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "records": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
