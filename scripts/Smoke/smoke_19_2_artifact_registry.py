from __future__ import annotations

import pprint
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from models.capability_request import CapabilityRequest
from services.artifact_registry_service import ArtifactRegistryService
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.repository_visibility_service import RepositoryVisibilityService
from services.validation_operations_service import ValidationOperationsService


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "services").mkdir()
    (repo / "tests").mkdir()
    (repo / "scripts" / "Smoke").mkdir(parents=True)
    (repo / "services" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    (repo / "tests" / "test_sprint_19_0_repository_visibility.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (repo / "scripts" / "Smoke" / "smoke_19_0_repository_visibility.py").write_text("print('Smoke 19.0 PASS')\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial commit")
    return repo


def wait(service: ValidationOperationsService, run_id: str) -> dict:
    status = service.status(run_id)
    for _ in range(50):
        if status["status"] in {"PASS", "FAIL", "ERROR", "TIMEOUT"}:
            return status
        time.sleep(0.1)
        status = service.status(run_id)
    return status


def main() -> None:
    print("== Smoke 19.2: artifact registry foundation ==")
    with TemporaryDirectory() as tmp:
        repo = make_repo(Path(tmp))
        archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")
        validation_service = ValidationOperationsService(repo)
        started = validation_service.start_run(profile_id="SMOKE_19_0_REPOSITORY_VISIBILITY", agent_id="lex", session_id="S19_2")
        validation = wait(validation_service, started["run_id"])
        artifact_service = ArtifactRegistryService(repo)
        repository_artifacts = artifact_service.list_artifacts(artifact_category="repository")
        validation_artifacts = artifact_service.list_artifacts(artifact_category="validation")
        execution = CapabilityExecutionService(repo)
        listed = execution.execute(CapabilityRequest(capability_id="artifact.list", session_id="S19_2", agent_id="lex", arguments={"project_id": "Ageix", "artifact_category": "validation"}))
        audit = CapabilityAuditService(repo).list_records()
        summary = {
            "archive_artifact_id": archive.get("artifact_id"),
            "validation_status": validation.get("status"),
            "validation_artifact_id": validation.get("artifact_id"),
            "repository_artifact_count": repository_artifacts["count"],
            "validation_artifact_count": validation_artifacts["count"],
            "artifact_capability_count": listed.result["count"],
            "audited": bool(audit and audit[-1]["capability_id"] == "artifact.list"),
        }
        pprint.pprint(summary)
        assert str(summary["archive_artifact_id"]).startswith("ART-")
        assert summary["validation_status"] == "PASS"
        assert str(summary["validation_artifact_id"]).startswith("ART-")
        assert summary["repository_artifact_count"] == 1
        assert summary["validation_artifact_count"] == 1
        assert summary["artifact_capability_count"] == 1
        assert summary["audited"] is True
    print("Smoke 19.2 PASS: artifact registry, repository archive artifacts, validation artifacts, discovery, metadata, and audit validated.")


if __name__ == "__main__":
    main()
