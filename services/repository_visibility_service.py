from __future__ import annotations

import fnmatch
import json
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


REPOSITORY_ARCHIVE_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".git/*",
    "venv/*",
    ".venv/*",
    "env/*",
    ".env",
    ".env.*",
    "*/.env",
    "*/.env.*",
    "__pycache__/*",
    "*/__pycache__/*",
    "*/*.pyc",
    "*.pyc",
    ".pytest_cache/*",
    ".mypy_cache/*",
    ".ruff_cache/*",
    ".coverage",
    "htmlcov/*",
    ".ageix/runtime/*",
    ".ageix/instance/*",
    ".ageix/manifests/*",
    ".ageix/config/auth.json",
    ".ageix/verification/*",
    "*/scratch/*",
    "*/artifacts/*",
    ".ageix/certs/*",
    "certs/*",
    "secrets/*",
    "logs/*",
    "logFiles/*",
    "scratch/*",
    "artifacts/*",
    "*.log",
    "*.tmp",
    "*.patch",
    "*.zip",
    "*.pem",
    "*.key",
    "*.crt",
    "*.csr",
    "*.p12",
    "*.pfx",
    ".idea/*",
    ".vscode/*",
)


@dataclass(frozen=True)
class GitCommandResult:
    returncode: int
    stdout: str
    stderr: str


class RepositoryVisibilityService:
    """Read-only repository visibility service backed by fixed git commands."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.archive_root = self.repo_root / ".ageix" / "repository_archives"
        self.index_path = self.archive_root / "index.json"

    def info(self) -> dict[str, Any]:
        git_available = self._git_available()
        inside_work_tree = self._git(["rev-parse", "--is-inside-work-tree"]).stdout.strip() == "true" if git_available else False
        top_level = self._git(["rev-parse", "--show-toplevel"]).stdout.strip() if inside_work_tree else str(self.repo_root)
        current_branch = self.current_branch().get("branch") if inside_work_tree else None
        default_branch = self._default_branch() if inside_work_tree else None
        return {
            "summary": "git repository available" if inside_work_tree else "git repository metadata unavailable",
            "repository_root": str(self.repo_root),
            "git_top_level": top_level or str(self.repo_root),
            "git_available": git_available,
            "inside_work_tree": inside_work_tree,
            "current_branch": current_branch,
            "default_branch": default_branch,
        }

    def status(self) -> dict[str, Any]:
        branch = self.current_branch().get("branch")
        porcelain = self._git(["status", "--porcelain=v1", "--branch"]).stdout.splitlines()
        staged = modified = untracked = 0
        ahead = behind = 0
        for line in porcelain:
            if line.startswith("##"):
                ahead, behind = self._parse_ahead_behind(line)
                continue
            if line.startswith("??"):
                untracked += 1
                continue
            if len(line) >= 2:
                if line[0] != " ":
                    staged += 1
                if line[1] != " ":
                    modified += 1
        clean = staged == 0 and modified == 0 and untracked == 0
        return {
            "summary": "repository clean" if clean else "repository has local changes",
            "branch": branch,
            "clean": clean,
            "working_tree_state": "clean" if clean else "dirty",
            "modified_file_count": modified,
            "untracked_file_count": untracked,
            "staged_file_count": staged,
            "ahead": ahead,
            "behind": behind,
        }

    def current_branch(self) -> dict[str, Any]:
        result = self._git(["branch", "--show-current"])
        branch = result.stdout.strip() or self._git(["rev-parse", "--short", "HEAD"]).stdout.strip()
        return {"summary": f"current branch is {branch}" if branch else "current branch unavailable", "branch": branch}

    def list_branches(self) -> dict[str, Any]:
        result = self._git(["branch", "--format=%(refname:short)|%(objectname:short)|%(committerdate:iso8601)|%(subject)"])
        active = self.current_branch().get("branch")
        branches: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            name, sha, committed_at, subject = (line.split("|", 3) + ["", "", "", ""])[:4]
            if name:
                branches.append({"name": name, "active": name == active, "commit": sha, "committed_at": committed_at, "summary": subject})
        return {"summary": f"{len(branches)} local branches available", "active_branch": active, "branches": branches, "count": len(branches)}

    def history(self, *, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 10), 100))
        safe_offset = max(0, int(offset or 0))
        fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s"
        result = self._git(["log", f"--max-count={safe_limit}", f"--skip={safe_offset}", f"--format={fmt}"])
        commits = []
        for line in result.stdout.splitlines():
            parts = (line.split("\x1f") + [""] * 6)[:6]
            commits.append({"commit": parts[0], "short_commit": parts[1], "author": parts[2], "author_email": parts[3], "timestamp": parts[4], "summary": parts[5]})
        return {"summary": f"returned {len(commits)} recent commits", "commits": commits, "count": len(commits), "limit": safe_limit, "offset": safe_offset}

    def diff_summary(self) -> dict[str, Any]:
        files_result = self._git(["diff", "--name-status"])
        staged_files_result = self._git(["diff", "--cached", "--name-status"])
        stat_result = self._git(["diff", "--shortstat"])
        staged_stat_result = self._git(["diff", "--cached", "--shortstat"])
        changed_files = self._parse_name_status(files_result.stdout)
        staged_files = self._parse_name_status(staged_files_result.stdout)
        insertions, deletions = self._parse_shortstat(stat_result.stdout + "\n" + staged_stat_result.stdout)
        return {
            "summary": f"{len(changed_files) + len(staged_files)} changed file entries summarized",
            "changed_files": changed_files,
            "staged_files": staged_files,
            "changed_file_count": len(changed_files),
            "staged_file_count": len(staged_files),
            "insertions": insertions,
            "deletions": deletions,
            "full_diff_exposed": False,
        }

    def create_archive(self, *, paths: list[str] | None = None, archive_name: str | None = None) -> dict[str, Any]:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        requested_paths = [str(path).strip() for path in (paths or []) if str(path).strip()]
        roots = self._resolve_archive_roots(requested_paths)
        archive_id = f"REPOARCH-{uuid4().hex[:12].upper()}"
        safe_name = self._safe_archive_name(archive_name, archive_id)
        archive_path = self.archive_root / safe_name
        included_files: list[str] = []
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root in roots:
                if root.is_file():
                    candidates = [root]
                else:
                    candidates = [path for path in root.rglob("*") if path.is_file()]
                for file_path in candidates:
                    rel = file_path.relative_to(self.repo_root).as_posix()
                    if self._is_excluded(rel):
                        continue
                    zf.write(file_path, rel)
                    included_files.append(rel)
        record = {
            "archive_id": archive_id,
            "filename": archive_path.name,
            "path": str(archive_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "included_roots": requested_paths or ["."],
            "excluded_patterns_applied": len(REPOSITORY_ARCHIVE_EXCLUDE_PATTERNS),
            "file_count": len(included_files),
            "repository_cleanliness": self.status().get("working_tree_state"),
            "summary": f"created repository archive with {len(included_files)} files",
        }
        records = self._read_archive_index()
        records.append(record)
        self._write_archive_index(records)
        return record

    def list_archives(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        records = sorted(self._read_archive_index(), key=lambda item: str(item.get("created_at") or ""), reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {"summary": f"{len(records)} repository archives indexed", "archives": page, "count": len(page), "total_count": len(records), "limit": safe_limit, "offset": safe_offset}

    def _git_available(self) -> bool:
        try:
            subprocess.run(["git", "--version"], cwd=self.repo_root, capture_output=True, text=True, timeout=10, check=False)
            return True
        except Exception:
            return False

    def _git(self, args: list[str]) -> GitCommandResult:
        allowed = {"rev-parse", "status", "branch", "log", "diff", "symbolic-ref"}
        if not args or args[0] not in allowed:
            raise ValueError("git_command_not_allowed")
        completed = subprocess.run(["git", *args], cwd=self.repo_root, capture_output=True, text=True, timeout=20, check=False)
        if completed.returncode != 0 and args[0] not in {"diff", "symbolic-ref"}:
            # Keep capability deterministic even for source archives without .git metadata.
            return GitCommandResult(completed.returncode, completed.stdout, completed.stderr)
        return GitCommandResult(completed.returncode, completed.stdout, completed.stderr)

    def _default_branch(self) -> str | None:
        for args in (["symbolic-ref", "refs/remotes/origin/HEAD", "--short"], ["branch", "--format=%(refname:short)"]):
            result = self._git(args)
            value = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            if value.startswith("origin/"):
                return value.split("/", 1)[1]
            if value in {"main", "master"}:
                return value
        return None

    @staticmethod
    def _parse_ahead_behind(line: str) -> tuple[int, int]:
        ahead = behind = 0
        if "ahead " in line:
            ahead = int(line.split("ahead ", 1)[1].split("]", 1)[0].split(",", 1)[0])
        if "behind " in line:
            behind = int(line.split("behind ", 1)[1].split("]", 1)[0].split(",", 1)[0])
        return ahead, behind

    @staticmethod
    def _parse_name_status(output: str) -> list[dict[str, str]]:
        files = []
        for line in output.splitlines():
            status, _, path = line.partition("\t")
            if path:
                files.append({"path": path, "status": status})
        return files

    @staticmethod
    def _parse_shortstat(output: str) -> tuple[int, int]:
        insertions = deletions = 0
        for line in output.replace(",", "").splitlines():
            parts = line.split()
            for i, part in enumerate(parts):
                if part.startswith("insertion") and i > 0:
                    insertions += int(parts[i - 1])
                if part.startswith("deletion") and i > 0:
                    deletions += int(parts[i - 1])
        return insertions, deletions

    def _resolve_archive_roots(self, requested_paths: list[str]) -> list[Path]:
        if not requested_paths:
            return [self.repo_root]
        roots = []
        for raw in requested_paths:
            candidate = Path(raw)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("archive_path_must_be_repo_relative")
            resolved = (self.repo_root / candidate).resolve()
            if not resolved.is_relative_to(self.repo_root):
                raise ValueError("archive_path_outside_repository")
            if not resolved.exists():
                raise FileNotFoundError(f"archive_path_not_found:{raw}")
            roots.append(resolved)
        return roots

    def _is_excluded(self, rel_path: str) -> bool:
        normalized = rel_path.replace("\\", "/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in REPOSITORY_ARCHIVE_EXCLUDE_PATTERNS)

    @staticmethod
    def _safe_archive_name(archive_name: str | None, archive_id: str) -> str:
        if not archive_name:
            return f"{archive_id}.zip"
        name = Path(str(archive_name)).name
        if not name.endswith(".zip"):
            name = f"{name}.zip"
        return name

    def _read_archive_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_archive_index(self, records: list[dict[str, Any]]) -> None:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
