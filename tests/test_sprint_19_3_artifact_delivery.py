from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from services.artifact_delivery_service import ArtifactDeliveryService
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
    status = service.status(run_id)
    for _ in range(40):
        if status["status"] in {"PASS", "FAIL", "ERROR", "TIMEOUT"}:
            return status
        time.sleep(0.1)
        status = service.status(run_id)
    return status


def test_artifact_push_delivers_repository_archive_to_local_export(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")

    delivery = ArtifactDeliveryService(repo).push(artifact_id=archive["artifact_id"], destination="local_export")

    assert delivery["delivery_id"].startswith("DELIV-")
    assert delivery["artifact_id"] == archive["artifact_id"]
    assert delivery["destination"] == "local_export"
    assert delivery["status"] == "completed"
    delivered_path = repo / delivery["delivery_reference"]
    assert delivered_path.exists()
    assert delivered_path.is_file()
    assert delivered_path.parent == repo / ".ageix" / "artifact_deliveries" / "local_export"
    assert delivered_path.suffix == ".zip"


def test_artifact_delivery_get_and_list_are_summary_first(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")
    service = ArtifactDeliveryService(repo)
    delivery = service.push(artifact_id=archive["artifact_id"], destination="local_export")

    fetched = service.get_delivery(delivery["delivery_id"])
    listed = service.list_deliveries(artifact_id=archive["artifact_id"])

    assert fetched["delivery_id"] == delivery["delivery_id"]
    assert listed["count"] == 1
    assert listed["deliveries"][0]["delivery_id"] == delivery["delivery_id"]
    assert "metadata" not in listed["deliveries"][0]


def test_artifact_delivery_rejects_unsupported_destinations_and_non_artifacts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")
    service = ArtifactDeliveryService(repo)

    with pytest.raises(ValueError, match="artifact_delivery_destination_not_supported"):
        service.push(artifact_id=archive["artifact_id"], destination="http")
    with pytest.raises(ValueError, match="artifact_not_found"):
        service.push(artifact_id="ART-DOESNOTEXIST", destination="local_export")


def test_artifact_delivery_can_package_directory_artifacts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    validation_service = ValidationOperationsService(repo)
    started = validation_service.start_run(profile_id="SMOKE_19_0_REPOSITORY_VISIBILITY", agent_id="lex", session_id="S19_3")
    result = _wait_for_terminal(validation_service, started["run_id"])

    delivery = ArtifactDeliveryService(repo).push(artifact_id=result["artifact_id"], destination="local_export")

    delivered_path = repo / delivery["delivery_reference"]
    assert result["status"] == "PASS"
    assert delivered_path.exists()
    assert delivered_path.suffix == ".zip"
    assert delivery["metadata"]["delivery_kind"] == "zip_directory"


def test_artifact_delivery_capabilities_are_registered_and_audited(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")
    registry = CapabilityRegistryService(repo)
    execution = CapabilityExecutionService(repo)

    assert registry.exists("artifact.push")
    assert registry.exists("artifact.delivery.get")
    assert registry.exists("artifact.delivery.list")
    response = execution.execute(CapabilityRequest(capability_id="artifact.push", session_id="S19_3", agent_id="lex", arguments={"artifact_id": archive["artifact_id"], "destination": "local_export"}))

    assert response.success is True
    assert response.result["delivery_id"].startswith("DELIV-")
    delivery_id = response.result["delivery_id"]
    fetched = execution.execute(CapabilityRequest(capability_id="artifact.delivery.get", session_id="S19_3", agent_id="lex", arguments={"delivery_id": delivery_id}))
    assert fetched.success is True
    assert fetched.result["delivery_id"] == delivery_id
    records = CapabilityAuditService(repo).list_records()
    assert records[-1]["capability_id"] == "artifact.delivery.get"
    assert records[-1]["success"] is True


def test_artifact_delivery_mcp_tools_are_discoverable() -> None:
    registry = MCPToolRegistry()
    tools = {tool["tool_name"]: tool for tool in registry.discover(category="artifact_delivery")}

    assert "ageix.artifact.push" in tools
    assert "ageix.artifact.delivery.get" in tools
    assert "ageix.artifact.delivery.list" in tools
    assert tools["ageix.artifact.push"]["capability_id"] == "artifact.push"
