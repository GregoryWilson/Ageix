from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from models.artifact_delivery import ArtifactDeliveryRecord
from services.artifact_registry_service import ArtifactRegistryService


SUPPORTED_ARTIFACT_DELIVERY_DESTINATIONS = {"local_export"}


class ArtifactDeliveryService:
    """Governed delivery service for existing artifacts.

    Delivery is intentionally constrained. It only delivers artifacts already
    known to the artifact registry and never accepts arbitrary file paths.
    Sprint 19.3 supports local_export only.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.delivery_root = self.repo_root / ".ageix" / "artifact_deliveries"
        self.local_export_root = self.delivery_root / "local_export"
        self.index_path = self.delivery_root / "index.json"

    def push(self, *, artifact_id: str, destination: str = "local_export", project_id: str = "Ageix") -> dict[str, Any]:
        normalized_destination = str(destination or "local_export").strip().lower()
        if normalized_destination not in SUPPORTED_ARTIFACT_DELIVERY_DESTINATIONS:
            raise ValueError("artifact_delivery_destination_not_supported")

        artifact = ArtifactRegistryService(self.repo_root).get_artifact(str(artifact_id or ""))
        if artifact.get("status") != "available":
            raise ValueError("artifact_not_available_for_delivery")
        source = self._resolve_artifact_source(artifact)

        self._ensure_layout()
        record = ArtifactDeliveryRecord(
            artifact_id=str(artifact["artifact_id"]),
            destination="local_export",
            project_id=str(project_id or artifact.get("project_id") or "Ageix"),
            status="completed",
            summary=f"Delivered artifact {artifact['artifact_id']} to local_export.",
            metadata={
                "artifact_category": artifact.get("artifact_category"),
                "artifact_type": artifact.get("artifact_type"),
                "artifact_source_id": artifact.get("source_id"),
                "source_path": artifact.get("path"),
            },
        )
        delivery_path = self._delivery_path(record, source)
        if source.is_dir():
            self._zip_directory(source, delivery_path)
            delivery_kind = "zip_directory"
        else:
            shutil.copy2(source, delivery_path)
            delivery_kind = "file_copy"
        record.delivery_reference = delivery_path.relative_to(self.repo_root).as_posix()
        record.metadata["delivery_kind"] = delivery_kind
        record.metadata["filename"] = delivery_path.name
        record.metadata["size_bytes"] = delivery_path.stat().st_size if delivery_path.exists() else 0
        self._write_record(record)
        return record.to_detail(include_reference=False)

    def get_delivery(self, delivery_id: str, *, include_reference: bool = False) -> dict[str, Any]:
        return self._require_delivery(delivery_id).to_detail(include_reference=include_reference)

    def list_deliveries(
        self,
        *,
        artifact_id: str | None = None,
        destination: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        records = [ArtifactDeliveryRecord(**item) for item in self._read_index()]
        if artifact_id:
            records = [record for record in records if record.artifact_id == artifact_id]
        if destination:
            records = [record for record in records if record.destination == destination]
        if status:
            records = [record for record in records if record.status == status]
        if project_id:
            records = [record for record in records if record.project_id == project_id]
        records = sorted(records, key=lambda record: record.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} artifact delivery record(s) returned.",
            "deliveries": [record.to_summary() for record in page],
            "count": len(page),
            "total_count": len(records),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {
                "artifact_id": artifact_id,
                "destination": destination,
                "status": status,
                "project_id": project_id,
            },
        }

    def _ensure_layout(self) -> None:
        self.delivery_root.mkdir(parents=True, exist_ok=True)
        self.local_export_root.mkdir(parents=True, exist_ok=True)

    def _resolve_artifact_source(self, artifact: dict[str, Any]) -> Path:
        rel_path = artifact.get("path")
        if not rel_path:
            raise ValueError("artifact_has_no_deliverable_path")
        candidate = (self.repo_root / str(rel_path)).resolve()
        if not candidate.is_relative_to(self.repo_root):
            raise ValueError("artifact_path_outside_repository")
        if not candidate.exists():
            raise FileNotFoundError("artifact_source_not_found")
        return candidate

    def _delivery_path(self, record: ArtifactDeliveryRecord, source: Path) -> Path:
        suffix = ".zip" if source.is_dir() else (source.suffix or ".artifact")
        base_name = f"{record.delivery_id}_{record.artifact_id}{suffix}"
        return self.local_export_root / base_name

    def _zip_directory(self, source: Path, destination: Path) -> None:
        if destination.exists():
            raise ValueError("artifact_delivery_would_overwrite")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(source).as_posix())

    def _write_record(self, record: ArtifactDeliveryRecord) -> None:
        self._ensure_layout()
        record_path = self.delivery_root / f"{record.delivery_id}.json"
        if record_path.exists():
            raise ValueError("artifact_delivery_record_already_exists")
        record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        records = self._read_index()
        records.append(record.model_dump())
        self.index_path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")

    def _require_delivery(self, delivery_id: str) -> ArtifactDeliveryRecord:
        for item in self._read_index():
            if item.get("delivery_id") == delivery_id:
                return ArtifactDeliveryRecord(**item)
        raise ValueError("artifact_delivery_not_found")

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []
