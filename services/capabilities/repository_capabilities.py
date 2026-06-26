from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.repository_visibility_service import RepositoryVisibilityService


def register_capabilities(repo_root: Path):
    def service() -> RepositoryVisibilityService:
        return RepositoryVisibilityService(repo_root)

    def repo_info(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().info(), "metadata": {"request_mode": "repo_info", "repository_target": str(repo_root)}, "error": None}

    def repo_status(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().status(), "metadata": {"request_mode": "repo_status", "repository_target": str(repo_root)}, "error": None}

    def repo_branch_current(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().current_branch(), "metadata": {"request_mode": "repo_branch_current", "repository_target": str(repo_root)}, "error": None}

    def repo_branch_list(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().list_branches(), "metadata": {"request_mode": "repo_branch_list", "repository_target": str(repo_root)}, "error": None}

    def repo_history(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().history(limit=int(arguments.get("limit") or 10), offset=int(arguments.get("offset") or 0)), "metadata": {"request_mode": "repo_history", "repository_target": str(repo_root)}, "error": None}

    def repo_diff_summary(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().diff_summary(), "metadata": {"request_mode": "repo_diff_summary", "repository_target": str(repo_root)}, "error": None}

    def repo_archive_create(arguments: dict[str, Any]) -> dict[str, Any]:
        paths = arguments.get("paths") or None
        if paths is not None and not isinstance(paths, list):
            return {"success": False, "result": {}, "metadata": {"request_mode": "repo_archive_create"}, "error": "paths_must_be_list"}
        result = service().create_archive(paths=paths, archive_name=arguments.get("archive_name"))
        return {"success": True, "result": result, "metadata": {"request_mode": "repo_archive_create", "repository_target": str(repo_root)}, "error": None}

    def repo_archive_list(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": service().list_archives(limit=int(arguments.get("limit") or 20), offset=int(arguments.get("offset") or 0)), "metadata": {"request_mode": "repo_archive_list", "repository_target": str(repo_root)}, "error": None}

    return [
        (CapabilityDefinition(capability_id="repo.info", category="repository", access_level="governed_read", handler="repository.info", description="Return summary-first repository identity and git availability."), repo_info),
        (CapabilityDefinition(capability_id="repo.status", category="repository", access_level="governed_read", handler="repository.status", description="Return summary-first repository status and cleanliness."), repo_status),
        (CapabilityDefinition(capability_id="repo.branch.current", category="repository", access_level="governed_read", handler="repository.branch.current", description="Return the active repository branch."), repo_branch_current),
        (CapabilityDefinition(capability_id="repo.branch.list", category="repository", access_level="governed_read", handler="repository.branch.list", description="List local repository branches with summaries."), repo_branch_list),
        (CapabilityDefinition(capability_id="repo.history", category="repository", access_level="governed_read", handler="repository.history", description="Return paginated recent commit summaries."), repo_history),
        (CapabilityDefinition(capability_id="repo.diff.summary", category="repository", access_level="governed_read", handler="repository.diff.summary", description="Return changed-file and shortstat summaries without full diffs."), repo_diff_summary),
        (CapabilityDefinition(capability_id="repo.archive.create", category="repository", access_level="governed_read", handler="repository.archive.create", description="Create a governed repository archive for selected paths or the whole repo with static exclusions."), repo_archive_create),
        (CapabilityDefinition(capability_id="repo.archive.list", category="repository", access_level="governed_read", handler="repository.archive.list", description="List governed repository archives."), repo_archive_list),
    ]
