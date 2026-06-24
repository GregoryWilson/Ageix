from __future__ import annotations

import pprint
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from models.capability_request import CapabilityRequest
from services.artifact_delivery_service import ArtifactDeliveryService
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
    print("== Smoke 19.3: artifact delivery foundation ==")
    with TemporaryDirectory() as tmp:
        repo = make_repo(Path(tmp))
        archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")
        delivery_service = ArtifactDeliveryService(repo)
        delivery = delivery_service.push(artifact_id=archive["artifact_id"], destination="local_export")
        validation_service = ValidationOperationsService(repo)
        started = validation_service.start_run(profile_id="SMOKE_19_0_REPOSITORY_VISIBILITY", agent_id="lex", session_id="S19_3")
        validation = wait(validation_service, started["run_id"])
        validation_delivery = delivery_service.push(artifact_id=validation["artifact_id"], destination="local_export")
        execution = CapabilityExecutionService(repo)
        listed = execution.execute(CapabilityRequest(capability_id="artifact.delivery.list", session_id="S19_3", agent_id="lex", arguments={"artifact_id": archive["artifact_id"]}))
        fetched = execution.execute(CapabilityRequest(capability_id="artifact.delivery.get", session_id="S19_3", agent_id="lex", arguments={"delivery_id": delivery["delivery_id"]}))
        audit = CapabilityAuditService(repo).list_records()
        summary = {
            "archive_artifact_id": archive.get("artifact_id"),
            "archive_delivery_id": delivery.get("delivery_id"),
            "archive_delivery_exists": (repo / delivery["delivery_reference"]).exists(),
            "validation_status": validation.get("status"),
            "validation_artifact_id": validation.get("artifact_id"),
            "validation_delivery_id": validation_delivery.get("delivery_id"),
            "delivery_list_count": listed.result["count"],
            "delivery_get_status": fetched.result["status"],
            "audited": bool(audit and audit[-1]["capability_id"] == "artifact.delivery.get"),
        }
        pprint.pprint(summary)
        assert str(summary["archive_artifact_id"]).startswith("ART-")
        assert str(summary["archive_delivery_id"]).startswith("DELIV-")
        assert summary["archive_delivery_exists"] is True
        assert summary["validation_status"] == "PASS"
        assert str(summary["validation_artifact_id"]).startswith("ART-")
        assert str(summary["validation_delivery_id"]).startswith("DELIV-")
        assert summary["delivery_list_count"] == 1
        assert summary["delivery_get_status"] == "completed"
        assert summary["audited"] is True
    print("Smoke 19.3 PASS: artifact push, local export delivery, delivery get/list, validation artifact delivery, and audit validated.")


if __name__ == "__main__":
    main()
