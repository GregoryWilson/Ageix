from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.project_registry_service import ProjectRegistryService


class ProjectProfileService:
    def __init__(self, ageix_root: Path | str):
        self.registry_service = ProjectRegistryService(ageix_root)

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
        project = self.registry_service.register_project(
            project_id=project_id,
            name=name,
            project_type=project_type,
            root_path=root_path,
            project_role=project_role,
            status=status,
            metadata=metadata,
        )
        self.write_profile(project)
        return project

    def write_profile(self, project: dict[str, Any]) -> dict[str, Any]:
        brain_path = Path(project["brain_path"])
        profile_path = brain_path / "project_profile.json"

        brain_path.mkdir(parents=True, exist_ok=True)

        profile = {
            "schema_version": 1,
            "project_id": project["project_id"],
            "name": project["name"],
            "project_type": project["project_type"],
            "root_path": project["root_path"],
            "brain_path": project["brain_path"],
            "project_role": project["project_role"],
            "status": project["status"],
            "created_at": project["created_at"],
            "updated_at": project["updated_at"],
            "metadata": project["metadata"],
        }

        with profile_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, sort_keys=True)

        return profile

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self.registry_service.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        return self.registry_service.list_projects()

    def resolve_project(self, project_id: str) -> dict[str, str]:
        return self.registry_service.resolve_project(project_id)