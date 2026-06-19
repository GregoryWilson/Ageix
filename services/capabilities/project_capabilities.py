from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.project_profile_service import ProjectProfileService
from services.project_registry_service import ProjectRegistryService


def _safe_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": project.get("project_id"),
        "name": project.get("name"),
        "project_type": project.get("project_type"),
        "project_role": project.get("project_role"),
        "status": project.get("status"),
        "profile_available": True,
        "metadata": project.get("metadata", {}),
    }


def register_capabilities(repo_root: Path):
    def project_list(arguments: dict[str, Any]) -> dict[str, Any]:
        projects = [_safe_project(project) for project in ProjectRegistryService(repo_root).list_projects()]
        return {"success": True, "result": {"projects": projects}, "metadata": {"source": "project_registry"}}

    def project_profile(arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = str(arguments.get("project_id") or "")
        if not project_id:
            return {"success": False, "result": {}, "error": "project_id_required"}
        profile_service = ProjectProfileService(repo_root)
        profile = profile_service.get_project(project_id)
        safe = {
            key: value for key, value in profile.items()
            if key not in {"root_path", "brain_path"}
        }
        return {"success": True, "result": {"project_id": project_id, "profile": safe}, "metadata": {"source": "project_profile"}}

    return [
        (CapabilityDefinition(
            capability_id="project.list",
            category="project",
            access_level="read",
            handler="project.list",
            description="List governed projects known to Ageix.",
        ), project_list),
        (CapabilityDefinition(
            capability_id="project.profile",
            category="project",
            access_level="read",
            handler="project.profile",
            description="Return governed project profile metadata.",
        ), project_profile),
    ]
