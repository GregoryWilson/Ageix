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

    def validate_staged_patch(
        self,
        patch_id: str,
        validation_commands: list[str] | None = None,
    ) -> ValidationResult:
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

            test_results = []
            if validation_commands:
                from services.test_execution_service import TestExecutionService

                executor = TestExecutionService()
                test_results = executor.run_commands(
                    workspace_path=workspace_dir,
                    commands=validation_commands,
                )

            reasoning = [
                "Patch was successfully materialized into an isolated validation workspace.",
                "Live repository was not modified.",
            ]

            if test_results:
                if all(r.passed for r in test_results):
                    reasoning.append("All validation commands completed successfully.")
                else:
                    reasoning.append("One or more validation commands failed.")
            else:
                reasoning.append("No validation commands were executed.")

            test_output = "\n\n".join(
                f"COMMAND: {r.command}\n"
                f"RETURN CODE: {r.return_code}\n"
                f"DURATION: {r.duration_seconds}\n"
                f"STDOUT:\n{r.stdout}\n"
                f"STDERR:\n{r.stderr}\n"
                for r in test_results
            )

            test_output_path.write_text(test_output, encoding="utf-8")

            report = {
                "verification_id": verification_id,
                "patch_id": patch_id,
                "status": "materialized",
                "result": "WARN",
                "reasoning": reasoning,
                "workspace_path": str(workspace_dir),
                "patch_manifest": manifest,
                "test_results": [
                    {
                        "command": r.command,
                        "return_code": r.return_code,
                        "duration_seconds": r.duration_seconds,
                        "passed": r.passed,
                    }
                    for r in test_results
                        
                ],
                "result": "PASS" if test_results and all(r.passed for r in test_results) else "WARN",
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