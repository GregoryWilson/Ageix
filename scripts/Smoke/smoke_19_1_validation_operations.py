from __future__ import annotations

import pprint
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.validation_operations_service import ValidationOperationsService


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "tests").mkdir()
    (repo / "scripts" / "Smoke").mkdir(parents=True)
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
    print("== Smoke 19.1: governed validation operations ==")
    with TemporaryDirectory() as tmp:
        repo = make_repo(Path(tmp))
        service = ValidationOperationsService(repo)
        profiles = service.list_profiles()
        execution = CapabilityExecutionService(repo)
        start = execution.execute(CapabilityRequest(capability_id="validation.run.start", session_id="S19_1", agent_id="lex", arguments={"project_id": "Ageix", "profile_id": "SMOKE_19_0_REPOSITORY_VISIBILITY"}))
        result = wait(service, start.result["run_id"])
        history = service.history()
        audit = CapabilityAuditService(repo).list_records()
        summary = {
            "profile_count": profiles["count"],
            "run_id": start.result["run_id"],
            "start_returned_running": start.result["status"] == "RUNNING",
            "final_status": result["status"],
            "evidence_package_id": result.get("evidence_package_id"),
            "history_count": history["count"],
            "audited": bool(audit and audit[-1]["capability_id"] == "validation.run.start"),
            "shell_execution": service.get_profile("SMOKE_19_0_REPOSITORY_VISIBILITY")["shell_execution"],
        }
        pprint.pprint(summary)
        assert summary["profile_count"] >= 2
        assert summary["start_returned_running"] is True
        assert summary["final_status"] == "PASS"
        assert str(summary["evidence_package_id"]).startswith("EVPKG-")
        assert summary["audited"] is True
        assert summary["shell_execution"] is False
    print("Smoke 19.1 PASS: approved async validation profiles, result polling, evidence capture, history, and audit validated.")


if __name__ == "__main__":
    main()
