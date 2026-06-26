from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.artifact import ArtifactRecord, ArtifactReference


ARTIFACT_CATEGORIES = {"repository", "validation", "report", "patch", "other"}


class ArtifactRegistryService:
    """Governed registry for generated Ageix artifacts.

    Artifacts are immutable registry objects that may reference files, evidence,
    validation runs, proposals, or other governed objects. The registry does not
    upload, delete, edit, push, or publish artifacts.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.artifact_root = self.repo_root / ".ageix" / "artifacts"
        self.index_path = self.artifact_root / "index.json"

    def register_artifact(
        self,
        *,
        artifact_category: str,
        artifact_type: str,
        created_by: str,
        project_id: str = "Ageix",
        source_id: str | None = None,
        summary: str = "",
        path: str | Path | None = None,
        references: list[dict[str, Any] | ArtifactReference] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        category = self._normalize_category(artifact_category)
        rel_path = self._normalize_artifact_path(path)
        record = ArtifactRecord(
            artifact_category=category,
            artifact_type=artifact_type,
            created_by=created_by,
            project_id=str(project_id or "Ageix"),
            source_id=source_id,
            summary=summary,
            path=rel_path,
            references=[self._reference(ref) for ref in (references or [])],
            metadata=dict(metadata or {}),
        )
        self._ensure_layout()
        index = self._read_index()
        index.append(record.model_dump())
        self._write_index(index)
        self._write_record(record)
        return record.model_dump()

    def list_artifacts(
        self,
        *,
        artifact_category: str | None = None,
        artifact_type: str | None = None,
        source_id: str | None = None,
        created_by: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        records = [ArtifactRecord(**item) for item in self._read_index()]
        if artifact_category:
            records = [record for record in records if record.artifact_category == artifact_category]
        if artifact_type:
            records = [record for record in records if record.artifact_type == artifact_type]
        if source_id:
            records = [record for record in records if record.source_id == source_id]
        if created_by:
            records = [record for record in records if record.created_by == created_by]
        if project_id:
            records = [record for record in records if record.project_id == project_id]
        records = sorted(records, key=lambda record: record.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} artifact(s) returned.",
            "artifacts": [record.to_summary() for record in page],
            "count": len(page),
            "total_count": len(records),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {
                "artifact_category": artifact_category,
                "artifact_type": artifact_type,
                "source_id": source_id,
                "created_by": created_by,
                "project_id": project_id,
            },
        }

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        return self._require_artifact(artifact_id).model_dump()

    def metadata(self, artifact_id: str) -> dict[str, Any]:
        record = self._require_artifact(artifact_id)
        return {
            **record.to_summary(),
            "path": record.path,
            "references": [ref.model_dump() for ref in record.references],
            "metadata": record.metadata,
        }

    def _ensure_layout(self) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        for category in sorted(ARTIFACT_CATEGORIES):
            (self.artifact_root / category).mkdir(parents=True, exist_ok=True)

    def _normalize_category(self, category: str) -> str:
        normalized = str(category or "other").strip().lower() or "other"
        if normalized not in ARTIFACT_CATEGORIES:
            normalized = "other"
        return normalized

    def _normalize_artifact_path(self, path: str | Path | None) -> str | None:
        if path is None:
            return None
        candidate = Path(path)
        resolved = candidate if candidate.is_absolute() else (self.repo_root / candidate)
        resolved = resolved.resolve()
        if not resolved.is_relative_to(self.repo_root):
            raise ValueError("artifact_path_must_be_inside_repository")
        return resolved.relative_to(self.repo_root).as_posix()

    def _reference(self, value: dict[str, Any] | ArtifactReference) -> ArtifactReference:
        if isinstance(value, ArtifactReference):
            return value
        return ArtifactReference(**value)

    def _require_artifact(self, artifact_id: str) -> ArtifactRecord:
        for item in self._read_index():
            if item.get("artifact_id") == artifact_id:
                return ArtifactRecord(**item)
        raise ValueError("artifact_not_found")

    def _record_path(self, record: ArtifactRecord) -> Path:
        return self.artifact_root / record.artifact_category / f"{record.artifact_id}.json"

    def _write_record(self, record: ArtifactRecord) -> None:
        path = self._record_path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("artifact_record_already_exists")
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_index(self, records: list[dict[str, Any]]) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
