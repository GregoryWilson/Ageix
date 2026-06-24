from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.repository_visibility_service import RepositoryVisibilityService
from ageix_mcp.tool_registry import MCPToolRegistry


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "services").mkdir()
    (repo / "services" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    (repo / "services" / "alpha.py").write_text("print('alpha2')\n", encoding="utf-8")
    (repo / "scratch").mkdir()
    (repo / "scratch" / "secret.tmp").write_text("skip", encoding="utf-8")
    (repo / ".env").write_text("SECRET=yes", encoding="utf-8")
    return repo


def test_repository_visibility_service_reports_status_history_and_diff(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = RepositoryVisibilityService(repo)

    info = service.info()
    status = service.status()
    history = service.history(limit=5)
    diff = service.diff_summary()

    assert info["inside_work_tree"] is True
    assert status["branch"] == "main"
    assert status["modified_file_count"] == 1
    assert history["commits"][0]["summary"] == "initial commit"
    assert diff["full_diff_exposed"] is False
    assert diff["changed_files"][0]["path"] == "services/alpha.py"


def test_repository_archive_create_supports_selected_paths_and_static_exclusions(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = RepositoryVisibilityService(repo)

    result = service.create_archive(paths=["services"], archive_name="services_only.zip")

    archive_path = Path(result["path"])
    assert archive_path.exists()
    assert result["included_roots"] == ["services"]
    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
    assert "services/alpha.py" in names
    assert ".env" not in names
    assert "scratch/secret.tmp" not in names


def test_repository_capabilities_are_registered_and_audited(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    registry = CapabilityRegistryService(repo)
    execution = CapabilityExecutionService(repo)

    assert registry.exists("repo.status")
    response = execution.execute(CapabilityRequest(capability_id="repo.status", session_id="S19", agent_id="lex", arguments={"project_id": "Ageix"}))

    assert response.success is True
    assert response.result["branch"] == "main"
    records = CapabilityAuditService(repo).list_records()
    assert records[-1]["capability_id"] == "repo.status"
    assert records[-1]["success"] is True


def test_repository_mcp_tools_are_discoverable() -> None:
    registry = MCPToolRegistry()
    tools = {tool["tool_name"]: tool for tool in registry.discover(category="repository")}

    assert "ageix.repo.status" in tools
    assert "ageix.repo.archive.create" in tools
    assert tools["ageix.repo.diff.summary"]["capability_id"] == "repo.diff.summary"
