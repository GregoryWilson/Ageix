from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Literal, Any
import json
from pathlib import Path


PatchStatus = Literal[
    "draft",
    "staged",
    "tested",
    "approved",
    "committed",
    "pushed",
    "rolled_back",
]


@dataclass
class PatchFile:
    path: str
    operation: Literal["create", "modify", "delete"]
    original_hash: str | None = None
    staged_hash: str | None = None


@dataclass
class PatchManifest:
    patch_id: str
    status: PatchStatus
    summary: str
    created_by: str
    conversation_id: str | None = None
    work_order_id: str | None = None
    files: list[PatchFile] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    tests_run: list[dict[str, Any]] = field(default_factory=list)
    proposal_quality: dict[str, Any] | None = None
    requirement_trace: dict[str, Any] | None = None
    behavior_verification: dict[str, Any] | None = None
    validation_summary: dict[str, Any] | None = None
    validation_evidence: dict[str, Any] | None = None
    git_commit: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")