from __future__ import annotations

import subprocess
from pathlib import Path


class GitService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(message)

        return result.stdout.strip()

    def status_short(self) -> str:
        return self._run(["status", "--short"])

    def diff(self, *paths: str) -> str:
        args = ["diff", *paths]
        return self._run(args)

    def current_branch(self) -> str:
        return self._run(["branch", "--show-current"])

    def current_commit(self) -> str:
        return self._run(["rev-parse", "HEAD"])

    def add(self, *paths: str) -> str:
        return self._run(["add", *paths])

    def commit(self, message: str) -> str:
        self._run(["commit", "-m", message])
        return self.current_commit()

    def commit_paths(self, message: str, paths: list[str]) -> str:
        self.add(*paths)
        return self.commit(message)

    def rollback_soft_last_commit(self) -> str:
        return self._run(["reset", "--soft", "HEAD~1"])

    def rollback_hard_last_commit(self) -> str:
        return self._run(["reset", "--hard", "HEAD~1"])

    def create_branch(self, branch_name: str) -> str:
        return self._run(["checkout", "-b", branch_name])

    def checkout_branch(self, branch_name: str) -> str:
        return self._run(["checkout", branch_name])

    def push_current_branch(self, remote: str = "origin") -> str:
        branch = self.current_branch()
        return self._run(["push", "-u", remote, branch])