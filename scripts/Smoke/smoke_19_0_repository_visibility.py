from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def build_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "smoke@example.com")
    git(repo, "config", "user.name", "Smoke Runner")
    (repo / "services").mkdir()
    (repo / "services" / "example.py").write_text("print('hello')\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "smoke baseline")
    (repo / "services" / "example.py").write_text("print('hello sprint 19')\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=excluded", encoding="utf-8")
    return repo


def execute(service: CapabilityExecutionService, capability_id: str, arguments: dict | None = None) -> dict:
    response = service.execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="SMOKE-19-0",
        agent_id="lex",
        arguments={"project_id": "Ageix", **(arguments or {})},
    ))
    assert response.success, response.error
    return response.result


def main() -> None:
    print("== Smoke 19.0: repository visibility foundation ==")
    with tempfile.TemporaryDirectory() as tmp:
        repo = build_repo(Path(tmp))
        service = CapabilityExecutionService(repo)
        status = execute(service, "repo.status")
        branch = execute(service, "repo.branch.current")
        history = execute(service, "repo.history", {"limit": 5})
        diff = execute(service, "repo.diff.summary")
        archive = execute(service, "repo.archive.create", {"paths": ["services"], "archive_name": "smoke_services.zip"})
        archives = execute(service, "repo.archive.list")
        pprint({
            "branch": branch["branch"],
            "clean": status["clean"],
            "modified_file_count": status["modified_file_count"],
            "history_count": history["count"],
            "diff_full_exposed": diff["full_diff_exposed"],
            "archive_file_count": archive["file_count"],
            "archive_count": archives["total_count"],
        })
        assert branch["branch"] == "main"
        assert status["clean"] is False
        assert history["count"] == 1
        assert diff["full_diff_exposed"] is False
        assert archive["file_count"] == 1
    print("Smoke 19.0 PASS: repository status, branch, history, diff summary, archive creation/list, and audit-backed capability execution validated.")


if __name__ == "__main__":
    main()
