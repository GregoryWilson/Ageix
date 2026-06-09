from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)


@dataclass
class Artifact:
    artifact_id: str
    artifact_type: str
    created_by: str
    content: dict[str, Any]
    created_at: str


def create_artifact(
    artifact_type: str,
    created_by: str,
    content: dict[str, Any],
) -> Artifact:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        artifact_type=artifact_type,
        created_by=created_by,
        content=content,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    path = ARTIFACT_DIR / f"{artifact.artifact_id}.json"
    path.write_text(json.dumps(asdict(artifact), indent=2), encoding="utf-8")
    return artifact


def load_artifact(artifact_id: str) -> Artifact:
    path = ARTIFACT_DIR / f"{artifact_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Artifact(**data)