from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from models.artifact import ArtifactReference
from models.patch_record import PatchRecord
from models.worker_context import WorkerContext
from services.artifact_registry_service import ArtifactRegistryService


PATCH_MAX_BYTES = 1024 * 1024
_PATCH_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class PatchRegistryService:
    """Governed registry for patch packages written by PatchWriterWorker."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.patch_root = self.repo_root / ".ageix" / "patches"
        self.index_path = self.patch_root / "index.json"

    def create_patch(
        self,
        *,
        patch_name: str,
        patch_content: str,
        summary: str = "",
        project_id: str = "Ageix",
        worker_context: WorkerContext | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content = str(patch_content or "")
        byte_count = len(content.encode("utf-8"))
        if byte_count <= 0:
            raise ValueError("patch_content_required")
        if byte_count > PATCH_MAX_BYTES:
            raise ValueError("patch_content_exceeds_1mb_limit")
        self._validate_patch_shape(content)

        safe_name = self._safe_patch_name(patch_name)
        context = worker_context or WorkerContext(worker="PatchWriterWorker", project_id=str(project_id or "Ageix"))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        line_count = len(content.splitlines())
        file_count_estimate = self._estimate_file_count(content)

        record = PatchRecord(
            patch_name=safe_name,
            project_id=str(project_id or "Ageix"),
            summary=str(summary or f"Stored governed patch {safe_name}."),
            patch_path="pending",
            metadata_path="pending",
            content_sha256=content_hash,
            line_count=line_count,
            byte_count=byte_count,
            file_count_estimate=file_count_estimate,
            worker_context=context.to_summary(),
            metadata=dict(metadata or {}),
        )
        patch_dir = self.patch_root / record.patch_id
        patch_path = patch_dir / "patch.diff"
        metadata_path = patch_dir / "metadata.json"
        record.patch_path = patch_path.relative_to(self.repo_root).as_posix()
        record.metadata_path = metadata_path.relative_to(self.repo_root).as_posix()

        self._ensure_layout()
        if patch_dir.exists():
            raise ValueError("patch_id_collision")
        patch_dir.mkdir(parents=True, exist_ok=False)
        patch_path.write_text(content, encoding="utf-8")

        artifact = ArtifactRegistryService(self.repo_root).register_artifact(
            artifact_category="patch",
            artifact_type="patch_package",
            created_by="patch.create",
            project_id=record.project_id,
            source_id=record.patch_id,
            summary=record.summary,
            path=patch_path,
            references=[ArtifactReference(reference_type="patch", reference_id=record.patch_id, relationship="describes")],
            metadata={
                "patch_id": record.patch_id,
                "patch_name": record.patch_name,
                "content_sha256": record.content_sha256,
                "line_count": record.line_count,
                "byte_count": record.byte_count,
                "file_count_estimate": record.file_count_estimate,
                "validation_status": record.validation_status,
            },
        )
        record.artifact_id = str(artifact.get("artifact_id"))
        metadata_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        index = self._read_index()
        index.append(record.model_dump())
        self._write_index(index)
        return {
            **record.to_summary(),
            "summary": f"Stored governed patch {record.patch_id} with {record.line_count} lines.",
        }

    def get_patch(self, patch_id: str, *, include_content: bool = False) -> dict[str, Any]:
        record = self._require_patch(patch_id)
        payload = record.to_metadata()
        payload["has_content"] = True
        if include_content:
            patch_path = (self.repo_root / record.patch_path).resolve()
            if not patch_path.is_relative_to(self.repo_root):
                raise ValueError("patch_path_outside_repository")
            payload["patch_content"] = patch_path.read_text(encoding="utf-8")
        return payload

    def metadata(self, patch_id: str) -> dict[str, Any]:
        record = self._require_patch(patch_id)
        return record.to_metadata()

    def list_patches(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        records = [PatchRecord(**item) for item in self._read_index()]
        if project_id:
            records = [record for record in records if record.project_id == project_id]
        if status:
            records = [record for record in records if record.status == status]
        if validation_status:
            records = [record for record in records if record.validation_status == validation_status]
        records = sorted(records, key=lambda record: record.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} patch package(s) returned.",
            "patches": [record.to_summary() for record in page],
            "count": len(page),
            "total_count": len(records),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {
                "project_id": project_id,
                "status": status,
                "validation_status": validation_status,
            },
        }

    def _validate_patch_shape(self, content: str) -> None:
        has_git_header = "diff --git " in content
        has_file_headers = "--- " in content and "+++ " in content
        has_hunk = "@@" in content
        if not ((has_git_header or has_file_headers) and has_hunk):
            raise ValueError("patch_content_must_look_like_unified_diff")

    def _estimate_file_count(self, content: str) -> int:
        files = {line for line in content.splitlines() if line.startswith("diff --git ")}
        if files:
            return len(files)
        plus_headers = [line for line in content.splitlines() if line.startswith("+++ ")]
        return len(plus_headers)

    def _safe_patch_name(self, patch_name: str) -> str:
        raw = str(patch_name or "patch.diff").strip() or "patch.diff"
        name = Path(raw).name
        name = _PATCH_NAME_RE.sub("_", name).strip("._") or "patch.diff"
        if not name.endswith((".patch", ".diff")):
            name = f"{name}.patch"
        return name[:160]

    def _ensure_layout(self) -> None:
        self.patch_root.mkdir(parents=True, exist_ok=True)

    def _require_patch(self, patch_id: str) -> PatchRecord:
        for item in self._read_index():
            if item.get("patch_id") == patch_id:
                return PatchRecord(**item)
        raise ValueError("patch_not_found")

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_index(self, records: list[dict[str, Any]]) -> None:
        self.patch_root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
