from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_OBJECTIVE = "Create foundational project identity layer for Ageix"
DEFAULT_OBJECTIVE_FILE = Path(".ageix/objectives/current_objective.txt")


@dataclass(frozen=True)
class ObjectiveEnvelope:
    objective_id: str
    title: str
    description: str
    project_id: str = "ageix"
    source: str = "default"
    priority: int = 1
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObjectiveSourceService:
    def __init__(
        self,
        repo_root: Path | str = ".",
        default_objective: str = DEFAULT_OBJECTIVE,
        default_objective_file: Path | str = DEFAULT_OBJECTIVE_FILE,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.default_objective = default_objective
        self.default_objective_file = Path(default_objective_file)

    def resolve_objective(
        self,
        objective_text: str | None = None,
        objective_file: Path | str | None = None,
        project_id: str = "ageix",
    ) -> dict[str, Any]:
        if objective_text and objective_text.strip():
            return self.from_text(
                objective_text,
                source="cli",
                project_id=project_id,
            ).to_dict()

        selected_file = Path(objective_file) if objective_file else self.default_objective_file
        file_envelope = self.from_file(selected_file, project_id=project_id)

        if file_envelope is not None:
            return file_envelope.to_dict()

        return self.default_objective_envelope(project_id=project_id).to_dict()

    def from_text(
        self,
        text: str,
        source: str = "text",
        project_id: str = "ageix",
        metadata: dict[str, Any] | None = None,
    ) -> ObjectiveEnvelope:
        normalized = text.strip()
        title = self._first_line(normalized)

        return ObjectiveEnvelope(
            objective_id=self._objective_id(source, normalized),
            title=title,
            description=normalized,
            project_id=project_id,
            source=source,
            priority=1,
            tags=[],
            metadata=metadata or {},
        )

    def from_file(
        self,
        file_path: Path | str,
        project_id: str = "ageix",
    ) -> ObjectiveEnvelope | None:
        path = self._resolve_path(file_path)

        if not path.exists() or not path.is_file():
            return None

        content = path.read_text(encoding="utf-8").strip()

        if not content:
            return None

        return self.from_text(
            content,
            source="file",
            project_id=project_id,
            metadata={"path": str(path)},
        )

    def default_objective_envelope(
        self,
        project_id: str = "ageix",
    ) -> ObjectiveEnvelope:
        return self.from_text(
            self.default_objective,
            source="default",
            project_id=project_id,
        )

    def _resolve_path(self, file_path: Path | str) -> Path:
        path = Path(file_path)

        if path.is_absolute():
            return path

        return self.repo_root / path

    @staticmethod
    def _first_line(text: str) -> str:
        return text.splitlines()[0].strip()

    @staticmethod
    def _objective_id(source: str, text: str) -> str:
        import hashlib

        digest = hashlib.sha1(f"{source}:{text}".encode("utf-8")).hexdigest()[:12]
        return f"objective_{digest}"