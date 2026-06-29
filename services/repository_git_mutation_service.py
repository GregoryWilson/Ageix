from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.repository_visibility_service import RepositoryVisibilityService

_REF_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


@dataclass(frozen=True)
class GitCommandResult:
    returncode: int
    stdout: str
    stderr: str


def _validate_ref_name(value: str, field: str) -> str:
    value = str(value or "").strip()
    if not value or not _REF_NAME_PATTERN.match(value) or ".." in value or value.startswith("-"):
        raise ValueError(f"invalid_{field}")
    return value


class RepositoryGitMutationService:
    """Executes a fixed, parameterized set of mutating git operations.

    Every method maps to one specific git operation with structured
    arguments only -- no raw command strings are ever accepted from a
    caller. Authorization (grant/approval) is enforced by the capability
    layer before any method here is invoked.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.visibility = RepositoryVisibilityService(self.repo_root)

    def fetch(self, remote: str = "origin") -> dict[str, Any]:
        remote = _validate_ref_name(remote, "remote")
        result = self._git(["fetch", remote])
        return {
            "summary": "fetch completed" if result.returncode == 0 else "fetch failed",
            "remote": remote,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def pull(self, remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
        remote = _validate_ref_name(remote, "remote")
        args = ["pull", "--ff-only", remote]
        if branch:
            args.append(_validate_ref_name(branch, "branch"))
        result = self._git(args)
        return {
            "summary": "pull completed (fast-forward only)" if result.returncode == 0 else "pull failed",
            "remote": remote,
            "branch": branch,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def checkout(self, ref: str, create: bool = False) -> dict[str, Any]:
        ref = _validate_ref_name(ref, "ref")
        args = ["checkout", "-b", ref] if create else ["checkout", ref]
        result = self._git(args)
        return {
            "summary": f"checked out {ref}" if result.returncode == 0 else "checkout failed",
            "ref": ref,
            "created": create,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def branch_create(self, name: str, start_point: str | None = None) -> dict[str, Any]:
        name = _validate_ref_name(name, "branch_name")
        args = ["branch", name]
        if start_point:
            args.append(_validate_ref_name(start_point, "start_point"))
        result = self._git(args)
        return {
            "summary": f"created branch {name}" if result.returncode == 0 else "branch create failed",
            "branch": name,
            "start_point": start_point,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def branch_delete(self, name: str) -> dict[str, Any]:
        name = _validate_ref_name(name, "branch_name")
        result = self._git(["branch", "-d", name])
        return {
            "summary": f"deleted branch {name}" if result.returncode == 0 else "branch delete failed",
            "branch": name,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def tag_create(self, name: str, message: str | None = None, ref: str | None = None) -> dict[str, Any]:
        name = _validate_ref_name(name, "tag_name")
        args = ["tag"]
        if message:
            args += ["-a", name, "-m", message]
        else:
            args.append(name)
        if ref:
            args.append(_validate_ref_name(ref, "ref"))
        result = self._git(args)
        return {
            "summary": f"created tag {name}" if result.returncode == 0 else "tag create failed",
            "tag": name,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def tag_delete(self, name: str) -> dict[str, Any]:
        name = _validate_ref_name(name, "tag_name")
        result = self._git(["tag", "-d", name])
        return {
            "summary": f"deleted tag {name}" if result.returncode == 0 else "tag delete failed",
            "tag": name,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def tag_list(self) -> dict[str, Any]:
        result = self._git(["tag", "--format=%(refname:short)|%(objectname:short)|%(creatordate:iso8601)"])
        tags = []
        for line in result.stdout.splitlines():
            name, sha, created_at = (line.split("|", 2) + ["", ""])[:3]
            if name:
                tags.append({"name": name, "commit": sha, "created_at": created_at})
        return {"summary": f"{len(tags)} tags available", "tags": tags, "count": len(tags)}

    def commit(self, message: str, paths: list[str] | None = None) -> dict[str, Any]:
        message = str(message or "").strip()
        if not message:
            raise ValueError("commit_message_required")
        if paths:
            add_args = ["add", "--"] + [self._validate_repo_relative_path(path) for path in paths]
            add_result = self._git(add_args)
            if add_result.returncode != 0:
                return {
                    "summary": "git add failed before commit",
                    "returncode": add_result.returncode,
                    "output": (add_result.stdout + add_result.stderr).strip(),
                }
        result = self._git(["commit", "-m", message])
        commit_sha = self._git(["rev-parse", "--short", "HEAD"]).stdout.strip() if result.returncode == 0 else None
        return {
            "summary": f"committed {commit_sha}" if result.returncode == 0 else "commit failed",
            "commit": commit_sha,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def push(self, remote: str = "origin", branch: str | None = None, set_upstream: bool = True) -> dict[str, Any]:
        remote = _validate_ref_name(remote, "remote")
        target_branch = _validate_ref_name(branch, "branch") if branch else self.visibility.current_branch().get("branch")
        if not target_branch:
            raise ValueError("branch_required")
        default_branch = self.visibility.info().get("default_branch")
        if default_branch and target_branch == default_branch:
            raise ValueError("use_repo.push.main_for_default_branch")
        args = ["push"]
        if set_upstream:
            args.append("-u")
        args += [remote, target_branch]
        result = self._git(args)
        return {
            "summary": f"pushed {target_branch} to {remote}" if result.returncode == 0 else "push failed",
            "remote": remote,
            "branch": target_branch,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def push_main(self, remote: str = "origin") -> dict[str, Any]:
        remote = _validate_ref_name(remote, "remote")
        default_branch = self.visibility.info().get("default_branch")
        if not default_branch:
            raise ValueError("default_branch_unresolved")
        result = self._git(["push", remote, default_branch])
        return {
            "summary": f"pushed {default_branch} to {remote}" if result.returncode == 0 else "push to default branch failed",
            "remote": remote,
            "branch": default_branch,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip(),
        }

    def _validate_repo_relative_path(self, raw: str) -> str:
        candidate = Path(str(raw))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("commit_path_must_be_repo_relative")
        resolved = (self.repo_root / candidate).resolve()
        if not resolved.is_relative_to(self.repo_root):
            raise ValueError("commit_path_outside_repository")
        return str(candidate)

    _ALLOWED_COMMANDS = {"fetch", "pull", "checkout", "branch", "tag", "commit", "push", "add", "rev-parse"}

    def _git(self, args: list[str]) -> GitCommandResult:
        if not args or args[0] not in self._ALLOWED_COMMANDS:
            raise ValueError("git_mutation_command_not_allowed")
        completed = subprocess.run(["git", *args], cwd=self.repo_root, capture_output=True, text=True, timeout=60, check=False)
        return GitCommandResult(completed.returncode, completed.stdout, completed.stderr)
