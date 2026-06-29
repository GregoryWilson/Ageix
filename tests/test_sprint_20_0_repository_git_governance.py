from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from models.capability_request import CapabilityRequest
from services.capabilities.repository_git_capabilities import register_capabilities
from services.capability_execution_service import CapabilityExecutionService
from services.repo_write_governance_service import (
    MUTATING_REPO_CAPABILITIES,
    NON_GRANTABLE_CAPABILITIES,
    RepoWriteGovernanceService,
)
from services.repository_git_mutation_service import RepositoryGitMutationService


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "file.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    return repo


def _capability_map(repo: Path):
    return dict((definition.capability_id, handler) for definition, handler in register_capabilities(repo))


def test_repo_fetch_and_tag_list_are_not_gated(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)

    fetch_result = caps["repo.fetch"]({})
    assert fetch_result["success"] is True

    tag_result = caps["repo.tag.list"]({})
    assert tag_result["success"] is True
    assert tag_result["result"]["count"] == 0


def test_mutating_capability_denied_without_grant_or_approval(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)

    result = caps["repo.branch.create"]({"name": "feature/x"})

    assert result["success"] is False
    assert result["error"] == "approval_or_sprint_grant_required"


def test_sprint_grant_authorizes_covered_mutating_capability(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)
    governance = RepoWriteGovernanceService(repo)

    governance.create_grant(sprint_id="SPRINT-1", granted_by="human", capability_ids=["repo.branch.create"])
    result = caps["repo.branch.create"]({"name": "feature/x", "sprint_id": "SPRINT-1"})

    assert result["success"] is True
    assert result["result"]["branch"] == "feature/x"
    assert result["result"]["authorization"]["source"] == "grant"


def test_sprint_grant_does_not_cover_uncovered_capability(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)
    governance = RepoWriteGovernanceService(repo)

    governance.create_grant(sprint_id="SPRINT-1", granted_by="human", capability_ids=["repo.branch.create"])
    result = caps["repo.tag.create"]({"name": "v1.0", "sprint_id": "SPRINT-1"})

    assert result["success"] is False
    assert result["error"] == "no_active_sprint_grant_for_capability"


def test_revoked_grant_no_longer_authorizes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)
    governance = RepoWriteGovernanceService(repo)

    grant = governance.create_grant(sprint_id="SPRINT-1", granted_by="human", capability_ids=["repo.branch.create"])
    governance.revoke_grant(grant["grant_id"], revoked_by="human")
    result = caps["repo.branch.create"]({"name": "feature/x", "sprint_id": "SPRINT-1"})

    assert result["success"] is False


def test_grant_creation_rejects_non_human_and_non_grantable_capabilities(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    governance = RepoWriteGovernanceService(repo)

    with pytest.raises(PermissionError):
        governance.create_grant(sprint_id="SPRINT-1", granted_by="agent", capability_ids=["repo.branch.create"])

    with pytest.raises(ValueError):
        governance.create_grant(sprint_id="SPRINT-1", granted_by="human", capability_ids=["repo.push.main"])


def test_one_off_approval_authorizes_a_single_call_then_is_consumed(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)
    governance = RepoWriteGovernanceService(repo)

    approval = governance.create_approval(capability_id="repo.commit", approved_by="human", reason="approved change")
    (repo / "file2.txt").write_text("world\n", encoding="utf-8")

    first = caps["repo.commit"]({"message": "second commit", "paths": ["file2.txt"], "approval_id": approval["approval_id"]})
    assert first["success"] is True
    assert first["result"]["authorization"]["source"] == "approval"

    second = caps["repo.commit"]({"message": "third commit", "approval_id": approval["approval_id"]})
    assert second["success"] is False
    assert second["error"] == "approval_already_consumed_or_revoked"


def test_push_main_is_never_grantable_and_always_needs_fresh_approval(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    caps = _capability_map(repo)
    governance = RepoWriteGovernanceService(repo)

    assert "repo.push.main" in NON_GRANTABLE_CAPABILITIES

    governance.create_grant(sprint_id="SPRINT-1", granted_by="human", capability_ids=list(MUTATING_REPO_CAPABILITIES - NON_GRANTABLE_CAPABILITIES))
    result = caps["repo.push.main"]({"sprint_id": "SPRINT-1"})

    assert result["success"] is False
    assert result["error"] == "fresh_human_approval_required"


def test_push_refuses_the_default_branch(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    governance = RepoWriteGovernanceService(repo)
    governance.create_approval(capability_id="repo.push", approved_by="human")
    git_service = RepositoryGitMutationService(repo)

    with pytest.raises(ValueError, match="use_repo.push.main_for_default_branch"):
        git_service.push(branch="main")


def test_commit_path_traversal_is_rejected(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    git_service = RepositoryGitMutationService(repo)

    with pytest.raises(ValueError, match="commit_path_must_be_repo_relative"):
        git_service.commit(message="bad", paths=["../outside.txt"])


def test_capability_execution_service_runs_repo_branch_create_through_full_pipeline(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    governance = RepoWriteGovernanceService(repo)
    governance.create_grant(sprint_id="SPRINT-1", granted_by="human", capability_ids=["repo.branch.create"])

    execution = CapabilityExecutionService(repo)
    response = execution.execute(CapabilityRequest(
        capability_id="repo.branch.create",
        agent_id="claude",
        session_id="S20_0",
        arguments={"name": "feature/full-pipeline", "sprint_id": "SPRINT-1"},
    ))

    assert response.success is True
    assert response.result["branch"] == "feature/full-pipeline"
