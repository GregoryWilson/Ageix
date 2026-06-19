from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.project_profile_service import ProjectProfileService
from services.project_registry_service import ProjectRegistryService
from services.current_project_resolution_service import CurrentProjectResolutionService


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
        if not project_id or project_id == "current":
            try:
                project_id = CurrentProjectResolutionService(repo_root).resolve_project_id(project_id or "current", str(arguments.get("session_id") or ""))
            except Exception as exc:
                return {"success": False, "result": {}, "error": str(exc)}
        profile_service = ProjectProfileService(repo_root)
        profile = profile_service.get_project(project_id)
        safe = {
            key: value for key, value in profile.items()
            if key not in {"root_path", "brain_path"}
        }
        return {"success": True, "result": {"project_id": project_id, "profile": safe}, "metadata": {"source": "project_profile"}}

    def project_current(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            project = CurrentProjectResolutionService(repo_root).current_project(str(arguments.get("session_id") or ""))
        except Exception as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": project, "metadata": {"source": "current_project_resolution"}}

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
        (CapabilityDefinition(
            capability_id="project.current",
            category="project",
            access_level="read",
            handler="project.current",
            description="Resolve the current project from session context or active project registry state.",
        ), project_current),
    ]
