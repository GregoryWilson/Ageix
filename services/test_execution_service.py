from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class CommandExecutionResult:
    command: str
    return_code: int
    duration_seconds: float
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.return_code == 0


from models.test_execution_evidence import (
    TestExecutionEvidence,
    TestExecutionResult,
    TestExecutionStatus,
    TestExecutionViolation,
)


class TestExecutionService:
    __test__ = False
    """Executes repository-discovered pytest tests and records runtime evidence."""

    def __init__(self, repo_root: Path | str = ".", timeout_seconds: float = 10.0) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.timeout_seconds = timeout_seconds


    def run_commands(
        self,
        *,
        workspace_path: Path | str,
        commands: list[str],
    ) -> list[CommandExecutionResult]:
        """Backward-compatible command runner for legacy staged-patch validation.

        Runtime validation for proposal acceptance is restricted to pytest identifiers
        through execute(). This method preserves the older ValidationService API.
        """
        results: list[CommandExecutionResult] = []
        workspace = Path(workspace_path).resolve()
        for command in commands:
            started = time.monotonic()
            completed = subprocess.run(
                command,
                cwd=workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            results.append(
                CommandExecutionResult(
                    command=command,
                    return_code=completed.returncode,
                    duration_seconds=round(time.monotonic() - started, 4),
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        return results

    def execute(
        self,
        test_identifiers: list[str],
        *,
        proposal: dict[str, Any] | None = None,
    ) -> TestExecutionResult:
        normalized = self._normalize_identifiers(test_identifiers)
        if not normalized:
            violation = TestExecutionViolation(
                code="NO_RUNTIME_EVIDENCE",
                message="No executable pytest test identifiers were available for runtime validation.",
                expected="At least one mapped pytest test identifier.",
                actual="<missing>",
                instruction="Provide executable test coverage and runtime validation evidence.",
            )
            return TestExecutionResult(status="fail", violations=[violation])

        runtime_evidence: list[TestExecutionEvidence] = []
        violations: list[TestExecutionViolation] = []

        with self._execution_workspace(proposal) as workspace:
            for identifier in normalized:
                evidence = self._run_pytest_identifier(workspace, identifier)
                runtime_evidence.append(evidence)
                violation = self._violation_for_evidence(evidence)
                if violation is not None:
                    violations.append(violation)

        return TestExecutionResult(
            status="fail" if violations else "pass",
            runtime_evidence=runtime_evidence,
            violations=violations,
        )

    def summarize(self, result: TestExecutionResult) -> dict[str, Any]:
        passed = sum(1 for item in result.runtime_evidence if item.status == TestExecutionStatus.PASSED)
        failed = sum(1 for item in result.runtime_evidence if item.status == TestExecutionStatus.FAILED)
        timed_out = sum(1 for item in result.runtime_evidence if item.status == TestExecutionStatus.TIMEOUT)
        not_found = sum(1 for item in result.runtime_evidence if item.status == TestExecutionStatus.NOT_FOUND)
        return {
            "status": result.status,
            "tests_executed": len(result.runtime_evidence),
            "tests_passed": passed,
            "tests_failed": failed,
            "tests_timed_out": timed_out,
            "tests_not_found": not_found,
            "violations": [violation.model_dump() for violation in result.violations],
        }

    def _run_pytest_identifier(self, cwd: Path, test_identifier: str) -> TestExecutionEvidence:
        started = time.monotonic()
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", test_identifier, "-q"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            duration = time.monotonic() - started
            status = TestExecutionStatus.PASSED if completed.returncode == 0 else TestExecutionStatus.FAILED
            combined = f"{completed.stdout}\n{completed.stderr}"
            if completed.returncode != 0 and self._looks_not_found(combined):
                status = TestExecutionStatus.NOT_FOUND
            return TestExecutionEvidence(
                test_identifier=test_identifier,
                status=status,
                duration_seconds=round(duration, 4),
                timestamp=timestamp,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            return TestExecutionEvidence(
                test_identifier=test_identifier,
                status=TestExecutionStatus.TIMEOUT,
                duration_seconds=round(duration, 4),
                timestamp=timestamp,
                stdout=self._decode_timeout_stream(exc.stdout),
                stderr=self._decode_timeout_stream(exc.stderr),
                returncode=None,
            )

    def _violation_for_evidence(self, evidence: TestExecutionEvidence) -> TestExecutionViolation | None:
        if evidence.status == TestExecutionStatus.PASSED:
            return None
        if evidence.status == TestExecutionStatus.NOT_FOUND:
            return TestExecutionViolation(
                code="TEST_NOT_FOUND",
                message="Mapped pytest test identifier could not be found.",
                test_identifier=evidence.test_identifier,
                expected="pytest can collect the mapped test identifier",
                actual="not_found",
                instruction="Provide an executable mapped pytest test identifier.",
            )
        if evidence.status == TestExecutionStatus.TIMEOUT:
            return TestExecutionViolation(
                code="TEST_TIMEOUT",
                message="Mapped pytest test timed out during runtime validation.",
                test_identifier=evidence.test_identifier,
                expected="test completes before timeout",
                actual="timeout",
                instruction="Investigate the timeout and provide a deterministic, bounded test.",
            )
        return TestExecutionViolation(
            code="TEST_EXECUTION_FAILED",
            message="Mapped pytest test failed during runtime validation.",
            test_identifier=evidence.test_identifier,
            expected="PASS",
            actual=evidence.status.value,
            instruction="Investigate the failing test and provide a corrected implementation.",
        )

    def _normalize_identifiers(self, identifiers: list[str]) -> list[str]:
        normalized: list[str] = []
        for identifier in identifiers:
            if not isinstance(identifier, str):
                continue
            cleaned = identifier.strip()
            if not cleaned or not self._is_allowed_pytest_identifier(cleaned):
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    def _is_allowed_pytest_identifier(self, identifier: str) -> bool:
        path = identifier.split("::", 1)[0].split(":", 1)[0].replace("\\", "/")
        return path.startswith("tests/") and path.endswith(".py")

    def _looks_not_found(self, output: str) -> bool:
        lowered = output.lower()
        return "not found" in lowered or "no tests ran" in lowered or "file or directory not found" in lowered

    def _decode_timeout_stream(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _execution_workspace(self, proposal: dict[str, Any] | None):
        service = self

        class WorkspaceContext:
            path: Path

            def __enter__(self) -> Path:
                if proposal is None:
                    self.path = service.repo_root
                    return self.path
                temp_dir = Path(tempfile.mkdtemp(prefix="ageix_runtime_validation_"))
                shutil.copytree(
                    service.repo_root,
                    temp_dir,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", ".ageix", "__pycache__", ".pytest_cache", "*.pyc", "ageix.db", "run.log"),
                )
                service._apply_proposal_overlay(temp_dir, proposal)
                self.path = temp_dir
                return self.path

            def __exit__(self, exc_type, exc, tb) -> None:
                if proposal is not None:
                    shutil.rmtree(self.path, ignore_errors=True)

        return WorkspaceContext()

    def _apply_proposal_overlay(self, workspace: Path, proposal: dict[str, Any]) -> None:
        for change in proposal.get("changes", []):
            if not isinstance(change, dict):
                continue
            operation = change.get("operation")
            if operation not in {"replace_file", "create_file"}:
                continue
            raw_path = change.get("path")
            content = change.get("content")
            if not isinstance(raw_path, str) or not isinstance(content, str):
                continue
            target = (workspace / raw_path).resolve()
            if not target.is_relative_to(workspace):
                raise ValueError(f"Path escapes runtime validation workspace: {raw_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not content.endswith("\n"):
                content += "\n"
            target.write_text(content, encoding="utf-8")
