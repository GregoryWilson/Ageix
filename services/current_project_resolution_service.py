from __future__ import annotations

from pathlib import Path
from typing import Any

from services.agent_session_service import AgentSessionService
from services.project_registry_service import ProjectRegistryError, ProjectRegistryService


class CurrentProjectResolutionService:
    """Resolves explicit, current, and session-bound project context."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = ProjectRegistryService(self.repo_root)
        self.sessions = AgentSessionService(self.repo_root)

    def resolve_project_id(self, project_id: str | None = None, session_id: str | None = None) -> str:
        explicit = (project_id or "").strip()
        if explicit and explicit != "current":
            self.registry.get_project(explicit)
            return explicit

        if session_id:
            session = self.sessions.get_session(session_id)
            if session and session.project_id:
                self.registry.get_project(session.project_id)
                return session.project_id

        projects = self.registry.list_projects()
        active = [project for project in projects if project.get("status") == "active"]
        if len(active) == 1:
            return str(active[0]["project_id"])
        if len(projects) == 1:
            return str(projects[0]["project_id"])
        if explicit == "current":
            raise ProjectRegistryError("current_project_not_resolved")
        raise ProjectRegistryError("project_id_required")

    def current_project(self, session_id: str | None = None) -> dict[str, Any]:
        project_id = self.resolve_project_id("current", session_id=session_id)
        project = self.registry.get_project(project_id)
        return {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "project_type": project.get("project_type"),
            "project_role": project.get("project_role"),
            "status": project.get("status"),
            "metadata": project.get("metadata", {}),
        }
