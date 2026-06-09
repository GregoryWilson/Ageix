from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.verification_result import VerificationResult, VerificationStatus


class VerificationResultLoader:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def load(self, verification_id: str) -> VerificationResult:
        verification_dir = self.repo_root / ".ageix" / "verification" / verification_id
        report_path = verification_dir / "report.json"
        test_output_path = verification_dir / "test_output.log"

        if not report_path.exists():
            raise FileNotFoundError(f"Verification report not found: {report_path}")

        report = self._read_json(report_path)
        test_output = self._read_text(test_output_path)

        status = self._normalize_status(report)
        patch_id = str(report.get("patch_id", ""))

        reasoning = report.get("reasoning", [])
        if not isinstance(reasoning, list):
            reasoning = [str(reasoning)]

        failure_summary = self._build_failure_summary(
            status=status,
            report=report,
            test_output=test_output,
        )

        return VerificationResult(
            verification_id=str(report.get("verification_id", verification_id)),
            patch_id=patch_id,
            status=status,
            failure_summary=failure_summary,
            evaluator_reasoning=[str(item) for item in reasoning],
            test_output=test_output,
            report_path=report_path,
            test_output_path=test_output_path,
            raw_report=report,
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Verification report must be a JSON object: {path}")

        return data

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""

        return path.read_text(encoding="utf-8", errors="replace")

    def _normalize_status(self, report: dict[str, Any]) -> VerificationStatus:
        raw_result = str(report.get("result", "")).upper().strip()

        if raw_result == "PASS":
            return VerificationStatus.PASS

        if raw_result == "WARN":
            return VerificationStatus.WARN

        if raw_result == "FAIL":
            return VerificationStatus.FAIL

        # Conservative default: unknown result should not be treated as passed.
        return VerificationStatus.FAIL

    def _build_failure_summary(
        self,
        status: VerificationStatus,
        report: dict[str, Any],
        test_output: str,
    ) -> str:
        if status == VerificationStatus.PASS:
            return ""

        explicit_summary = report.get("failure_summary")
        if explicit_summary:
            return str(explicit_summary)

        errors = report.get("errors")
        if isinstance(errors, list) and errors:
            return "\n".join(str(error) for error in errors)

        if test_output.strip():
            return test_output.strip()[-4000:]

        reasoning = report.get("reasoning")
        if isinstance(reasoning, list) and reasoning:
            return "\n".join(str(item) for item in reasoning)

        return "Verification failed, but no detailed failure output was available."