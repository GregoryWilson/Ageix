from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    verification_id: str
    status: str
    patch_id: str
    workspace_path: str
    report_path: str
    test_output_path: str


class ValidationService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.staged_root = self.repo_root / ".ageix" / "staged"
        self.verification_root = self.repo_root / ".ageix" / "verification"

    def validate_staged_patch(self, patch_id: str) -> ValidationResult:
        patch_dir = self.staged_root / patch_id
        manifest_path = patch_dir / "manifest.json"
        files_dir = patch_dir / "files"

        if not patch_dir.exists():
            raise FileNotFoundError(f"Patch artifact not found: {patch_dir}")

        if not manifest_path.exists():
            raise FileNotFoundError(f"Patch manifest not found: {manifest_path}")

        if not files_dir.exists():
            raise FileNotFoundError(f"Patch files directory not found: {files_dir}")

        manifest = self._load_json(manifest_path)

        verification_id = f"verification_{time.strftime('%Y%m%d_%H%M%S')}"
        verification_dir = self.verification_root / verification_id
        workspace_dir = verification_dir / "workspace"
        report_path = verification_dir / "report.json"
        test_output_path = verification_dir / "test_output.log"

        verification_dir.mkdir(parents=True, exist_ok=False)

        try:
            self._create_workspace(workspace_dir)
            self._overlay_patch_files(files_dir, workspace_dir)

            report = {
                "verification_id": verification_id,
                "patch_id": patch_id,
                "status": "materialized",
                "result": "WARN",
                "reasoning": [
                    "Patch was successfully materialized into an isolated validation workspace.",
                    "No tests were executed in this initial validation-service increment.",
                    "Live repository was not modified.",
                ],
                "workspace_path": str(workspace_dir),
                "patch_manifest": manifest,
                "test_results": [],
            }

            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            test_output_path.write_text("", encoding="utf-8")

            return ValidationResult(
                verification_id=verification_id,
                status="materialized",
                patch_id=patch_id,
                workspace_path=str(workspace_dir),
                report_path=str(report_path),
                test_output_path=str(test_output_path),
            )

        except Exception:
            if verification_dir.exists():
                shutil.rmtree(verification_dir, ignore_errors=True)
            raise

    def _create_workspace(self, workspace_dir: Path) -> None:
        ignore = shutil.ignore_patterns(
            ".git",
            ".ageix",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "venv",
            ".venv",
        )

        shutil.copytree(
            self.repo_root,
            workspace_dir,
            ignore=ignore,
        )

    def _overlay_patch_files(self, files_dir: Path, workspace_dir: Path) -> None:
        for source_path in files_dir.rglob("*"):
            if source_path.is_dir():
                continue

            relative_path = source_path.relative_to(files_dir)
            target_path = workspace_dir / relative_path

            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

    def _load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))