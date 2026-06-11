from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_PROJECT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}$")


class ProjectRegistryError(ValueError):
    pass


class ProjectRegistryService:
    def __init__(self, ageix_root: Path | str):
        self.ageix_root = Path(ageix_root).resolve()
        self.instance_path = self.ageix_root / ".ageix" / "instance"
        self.registry_path = self.instance_path / "workspace_registry.json"
        self.projects_path = self.ageix_root / ".ageix" / "projects"
        self.registry = self._load_registry()

    def register_project(
        self,
        project_id: str,
        name: str,
        project_type: str,
        root_path: Path | str,
        project_role: str = "target",
        status: str = "active",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_project_id(project_id)

        if project_id in self.registry["projects"]:
            raise ProjectRegistryError(f"Project already registered: {project_id}")

        now = self._now()
        root = Path(root_path).resolve()
        brain_path = self._brain_path(project_id)

        project = {
            "project_id": project_id,
            "name": name,
            "project_type": project_type,
            "root_path": str(root),
            "brain_path": str(brain_path),
            "project_role": project_role,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }

        self.registry["projects"][project_id] = project
        self.registry["updated_at"] = now
        self._write_registry()

        return project

    def get_project(self, project_id: str) -> dict[str, Any]:
        self._validate_project_id(project_id)

        try:
            return self.registry["projects"][project_id]
        except KeyError as exc:
            raise ProjectRegistryError(f"Unknown project_id: {project_id}") from exc

    def list_projects(self) -> list[dict[str, Any]]:
        return list(self.registry["projects"].values())

    def resolve_project(self, project_id: str) -> dict[str, str]:
        project = self.get_project(project_id)
        return {
            "project_id": project["project_id"],
            "root_path": project["root_path"],
            "brain_path": project["brain_path"],
        }

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            now = self._now()
            return {
                "schema_version": 1,
                "created_at": now,
                "updated_at": now,
                "projects": {},
            }

        with self.registry_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data.get("projects"), dict):
            raise ProjectRegistryError("Invalid registry: projects must be an object")

        return data

    def _write_registry(self) -> None:
        self.instance_path.mkdir(parents=True, exist_ok=True)
        with self.registry_path.open("w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2, sort_keys=True)

    def _brain_path(self, project_id: str) -> Path:
        return (self.projects_path / project_id).resolve()

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not isinstance(project_id, str) or not VALID_PROJECT_ID.fullmatch(project_id):
            raise ProjectRegistryError(f"Invalid project_id: {project_id!r}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()