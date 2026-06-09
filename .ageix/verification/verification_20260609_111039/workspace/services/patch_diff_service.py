from __future__ import annotations

import difflib
from pathlib import Path


class PatchDiffService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.stage_root = self.repo_root / ".ageix" / "staged"

    def _safe_repo_path(self, relative_path: str) -> Path:
        candidate = (self.repo_root / relative_path).resolve()

        if not candidate.is_relative_to(self.repo_root):
            raise ValueError(f"Path escapes repository root: {relative_path}")

        return candidate

    def _read_lines(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines(keepends=True)

    def generate_file_diff(self, patch_id: str, relative_path: str) -> str:
        repo_path = self._safe_repo_path(relative_path)
        staged_path = self.stage_root / patch_id / "files" / relative_path

        original_lines = self._read_lines(repo_path)
        staged_lines = self._read_lines(staged_path)

        return "".join(
            difflib.unified_diff(
                original_lines,
                staged_lines,
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
                lineterm="\n",
            )
        )

    def generate_patch_diff(self, patch_id: str, files: list[str]) -> str:
        diffs: list[str] = []

        for relative_path in files:
            file_diff = self.generate_file_diff(patch_id, relative_path)
            if file_diff.strip():
                diffs.append(file_diff)

        return "\n".join(diffs)

    def write_patch_diff(self, patch_id: str, files: list[str]) -> Path:
        diff_text = self.generate_patch_diff(patch_id, files)
        diff_path = self.stage_root / patch_id / "diff.patch"
        diff_path.write_text(diff_text, encoding="utf-8")
        return diff_path