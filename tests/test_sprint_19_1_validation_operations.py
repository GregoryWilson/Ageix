from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.validation_operations_service import ValidationOperationsService


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "tests").mkdir()
    (repo / "scripts" / "Smoke").mkdir(parents=True)
    (repo / "tests" / "test_sprint_19_0_repository_visibility.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (repo / "scripts" / "Smoke" / "smoke_19_0_repository_visibility.py").write_text("print('Smoke 19.0 PASS')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    return repo


def _wait_for_terminal(service: ValidationOperationsService, run_id: str) -> dict:
    result = service.status(run_id)
    for _ in range(30):
        if result["status"] in {"PASS", "FAIL", "ERROR", "TIMEOUT"}:
            return result
        time.sleep(0.1)
        result = service.status(run_id)
    return result


def test_validation_profiles_are_registered_and_command_summaries_only(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = ValidationOperationsService(repo)

    profiles = service.list_profiles()
    ids = {profile["profile_id"] for profile in profiles["profiles"]}

    assert "SMOKE_19_0_REPOSITORY_VISIBILITY" in ids
    assert "REGRESSION_CORE" in ids
    first = service.get_profile("SMOKE_19_0_REPOSITORY_VISIBILITY")
    assert first["shell_execution"] is False
    assert first["arguments_supported"] is False


def test_validation_run_starts_async_and_completes_with_evidence(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = ValidationOperationsService(repo)

    started = service.start_run(profile_id="SMOKE_19_0_REPOSITORY_VISIBILITY", agent_id="lex", session_id="S19_1")

    assert started["run_id"].startswith("VALRUN-")
    assert started["status"] == "RUNNING"
    result = _wait_for_terminal(service, started["run_id"])
    assert result["status"] == "PASS"
    assert result["evidence_package_id"].startswith("EVPKG-")
    assert (repo / ".ageix" / "evidence_packages" / result["evidence_package_id"] / "package.json").exists()


def test_validation_capabilities_are_audited(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    registry = CapabilityRegistryService(repo)
    execution = CapabilityExecutionService(repo)

    assert registry.exists("validation.profile.list")
    response = execution.execute(CapabilityRequest(capability_id="validation.run.start", session_id="S19_1", agent_id="lex", arguments={"project_id": "Ageix", "profile_id": "SMOKE_19_0_REPOSITORY_VISIBILITY"}))

    assert response.success is True
    assert response.result["status"] == "RUNNING"
    records = CapabilityAuditService(repo).list_records()
    assert records[-1]["capability_id"] == "validation.run.start"
    assert records[-1]["success"] is True


def test_validation_mcp_tools_are_discoverable() -> None:
    registry = MCPToolRegistry()
    tools = {tool["tool_name"]: tool for tool in registry.discover(category="validation")}

    assert "ageix.validation.profile.list" in tools
    assert "ageix.validation.run.start" in tools
    assert tools["ageix.validation.run.start"]["capability_id"] == "validation.run.start"
