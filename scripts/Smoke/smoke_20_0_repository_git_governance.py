from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.repo_write_governance_service import RepoWriteGovernanceService


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def build_repo(root: Path) -> Path:
    remote = root / "remote.git"
    git(root, "init", "--bare", "-b", "main", str(remote))

    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "smoke@example.com")
    git(repo, "config", "user.name", "Smoke Runner")
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "file.txt").write_text("hello\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "smoke baseline")
    git(repo, "push", "-u", "origin", "main")
    return repo


def execute(service: CapabilityExecutionService, capability_id: str, arguments: dict | None = None) -> dict:
    response = service.execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="SMOKE-20-0",
        agent_id="claude",
        arguments={"project_id": "Ageix", **(arguments or {})},
    ))
    return {"success": response.success, "error": response.error, "result": response.result}


def main() -> None:
    print("== Smoke 20.0: governed git management (sprint grants + one-off approvals) ==")
    with tempfile.TemporaryDirectory() as tmp:
        repo = build_repo(Path(tmp))
        service = CapabilityExecutionService(repo)
        governance = RepoWriteGovernanceService(repo)

        fetch = execute(service, "repo.fetch")
        assert fetch["success"], fetch["error"]
        assert fetch["result"]["returncode"] == 0

        denied = execute(service, "repo.branch.create", {"name": "feature/smoke"})
        assert denied["success"] is False
        assert denied["error"] == "approval_or_sprint_grant_required"

        governance.create_grant(sprint_id="SPRINT-SMOKE", granted_by="human", capability_ids=["repo.branch.create"])
        granted = execute(service, "repo.branch.create", {"name": "feature/smoke", "sprint_id": "SPRINT-SMOKE"})
        assert granted["success"], granted["error"]

        denied_main = execute(service, "repo.push.main", {"sprint_id": "SPRINT-SMOKE"})
        assert denied_main["success"] is False
        assert denied_main["error"] == "fresh_human_approval_required"

        approval = governance.create_approval(capability_id="repo.commit", approved_by="human", reason="smoke commit")
        (repo / "file2.txt").write_text("world\n", encoding="utf-8")
        committed = execute(service, "repo.commit", {"message": "smoke commit", "paths": ["file2.txt"], "approval_id": approval["approval_id"]})
        assert committed["success"], committed["error"]

        reused = execute(service, "repo.commit", {"message": "smoke commit again", "approval_id": approval["approval_id"]})
        assert reused["success"] is False
        assert reused["error"] == "approval_already_consumed_or_revoked"

        pprint({
            "fetch_summary": fetch["result"]["summary"],
            "branch_created": granted["result"]["branch"],
            "push_main_blocked_reason": denied_main["error"],
            "commit": committed["result"]["commit"],
            "reused_approval_blocked_reason": reused["error"],
        })
    print("Smoke 20.0 PASS: fetch is ungated, mutating capabilities are denied without authorization, sprint grants authorize scoped capabilities, push.main never accepts a grant, and one-off approvals are single-use.")


if __name__ == "__main__":
    main()
