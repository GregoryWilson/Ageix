from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from services.artifact_registry_service import ArtifactRegistryService
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.repository_visibility_service import RepositoryVisibilityService
from services.validation_operations_service import ValidationOperationsService


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "services").mkdir()
    (repo / "tests").mkdir()
    (repo / "scripts" / "Smoke").mkdir(parents=True)
    (repo / "services" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    (repo / "tests" / "test_sprint_19_0_repository_visibility.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (repo / "scripts" / "Smoke" / "smoke_19_0_repository_visibility.py").write_text("print('Smoke 19.0 PASS')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    return repo


def _wait_for_terminal(service: ValidationOperationsService, run_id: str) -> dict:
    result = service.status(run_id)
    for _ in range(40):
        if result["status"] in {"PASS", "FAIL", "ERROR", "TIMEOUT"}:
            return result
        time.sleep(0.1)
        result = service.status(run_id)
    return result


def test_artifact_registry_registers_and_filters_records(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = ArtifactRegistryService(repo)

    created = service.register_artifact(
        artifact_category="repository",
        artifact_type="repository_archive",
        created_by="test",
        source_id="REPOARCH-1",
        summary="test archive",
        path=repo / "services",
        references=[{"reference_type": "repository_archive", "reference_id": "REPOARCH-1"}],
    )

    assert created["artifact_id"].startswith("ART-")
    assert (repo / ".ageix" / "artifacts" / "repository" / f"{created['artifact_id']}.json").exists()
    listed = service.list_artifacts(artifact_category="repository", source_id="REPOARCH-1")
    assert listed["count"] == 1
    assert listed["artifacts"][0]["artifact_type"] == "repository_archive"
    metadata = service.metadata(created["artifact_id"])
    assert metadata["reference_count"] == 1


def test_repository_archive_registers_artifact(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo_service = RepositoryVisibilityService(repo)

    archive = repo_service.create_archive(paths=["services"], archive_name="services_only.zip")

    assert archive["artifact_id"].startswith("ART-")
    artifact = ArtifactRegistryService(repo).get_artifact(archive["artifact_id"])
    assert artifact["artifact_category"] == "repository"
    assert artifact["artifact_type"] == "repository_archive"
    assert artifact["source_id"] == archive["archive_id"]


def test_validation_completion_registers_artifact(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = ValidationOperationsService(repo)

    started = service.start_run(profile_id="SMOKE_19_0_REPOSITORY_VISIBILITY", agent_id="lex", session_id="S19_2")
    result = _wait_for_terminal(service, started["run_id"])

    assert result["status"] == "PASS"
    assert result["artifact_id"].startswith("ART-")
    artifact = ArtifactRegistryService(repo).get_artifact(result["artifact_id"])
    assert artifact["artifact_category"] == "validation"
    assert artifact["artifact_type"] == "validation_output"
    assert artifact["source_id"] == result["run_id"]
    reference_ids = {ref["reference_id"] for ref in artifact["references"]}
    assert result["evidence_package_id"] in reference_ids


def test_artifact_capabilities_are_registered_and_audited(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    ArtifactRegistryService(repo).register_artifact(
        artifact_category="report",
        artifact_type="report",
        created_by="test",
        source_id="REPORT-1",
        summary="report artifact",
    )
    registry = CapabilityRegistryService(repo)
    execution = CapabilityExecutionService(repo)

    assert registry.exists("artifact.list")
    response = execution.execute(CapabilityRequest(capability_id="artifact.list", session_id="S19_2", agent_id="lex", arguments={"project_id": "Ageix", "artifact_category": "report"}))

    assert response.success is True
    assert response.result["count"] == 1
    records = CapabilityAuditService(repo).list_records()
    assert records[-1]["capability_id"] == "artifact.list"
    assert records[-1]["success"] is True


def test_artifact_mcp_tools_are_discoverable() -> None:
    registry = MCPToolRegistry()
    tools = {tool["tool_name"]: tool for tool in registry.discover(category="artifact")}

    assert "ageix.artifact.list" in tools
    assert "ageix.artifact.get" in tools
    assert "ageix.artifact.metadata" in tools
    assert tools["ageix.artifact.list"]["capability_id"] == "artifact.list"
