from __future__ import annotations

from pathlib import Path
from typing import Any

from models.worker_context import WorkerContext
from services.patch_registry_service import PatchRegistryService


class PatchWriterWorker:
    """Minimal operational worker that stores governed patch packages only."""

    worker_name = "PatchWriterWorker"

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = PatchRegistryService(self.repo_root)

    def create_patch(
        self,
        *,
        patch_name: str,
        patch_content: str,
        summary: str = "",
        project_id: str = "Ageix",
        agent_id: str = "unknown",
        client_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = WorkerContext(
            worker=self.worker_name,
            project_id=str(project_id or "Ageix"),
            agent_id=str(agent_id or "unknown"),
            client_id=client_id,
            session_id=session_id,
            metadata={"capability_id": "patch.create"},
        )
        return self.registry.create_patch(
            patch_name=patch_name,
            patch_content=patch_content,
            summary=summary,
            project_id=str(project_id or "Ageix"),
            worker_context=context,
            metadata=metadata,
        )

    def import_patch_file(
        self,
        *,
        patch_name: str,
        source_path: str | Path,
        summary: str = "",
        project_id: str = "Ageix",
        agent_id: str = "unknown",
        client_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = WorkerContext(
            worker=self.worker_name,
            project_id=str(project_id or "Ageix"),
            agent_id=str(agent_id or "unknown"),
            client_id=client_id,
            session_id=session_id,
            metadata={"capability_id": "patch.ingest"},
        )
        return self.registry.create_patch_from_file(
            patch_name=patch_name,
            source_path=source_path,
            summary=summary,
            project_id=str(project_id or "Ageix"),
            worker_context=context,
            metadata=metadata,
        )
