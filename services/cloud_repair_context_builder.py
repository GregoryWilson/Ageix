from __future__ import annotations

from typing import Any
from pathlib import Path
from services.controls_service import ControlsService

class CloudRepairContextBuilder:
    """Builds compact, cloud-safe repair escalation packets."""

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(repo_root)
        self.controls = ControlsService(self.repo_root)

    def build_packet(
        self,
        *,
        repair_loop_manifest: dict[str, Any],
        repository_evidence: dict[str, Any] | list[Any] | None = None,
        latest_validation_report: dict[str, Any] | None = None,
        max_error_chars: int | None = None,
        max_evidence_items: int | None = None,
    ) -> dict[str, Any]:
        attempts = repair_loop_manifest.get("attempts", [])

        effective_max_error_chars = (
            max_error_chars
            if max_error_chars is not None
            else self.controls.cloud.max_failure_summary_chars
        )

        effective_max_evidence_items = (
            max_evidence_items
            if max_evidence_items is not None
            else self.controls.cloud.max_evidence_items
        )

        return {
            "origin_verification_id": repair_loop_manifest.get("origin_verification_id"),
            "origin_patch_id": repair_loop_manifest.get("origin_patch_id"),
            "objective": repair_loop_manifest.get("objective"),
            "local_attempt_count": len(attempts),
            "local_repair_history": self._summarize_attempts(attempts),
            "latest_validation_failure": self._summarize_validation(
                latest_validation_report,
                max_error_chars=effective_max_error_chars,
            ),
            "repository_evidence": self._compact_evidence(
                repository_evidence,
                max_items=effective_max_evidence_items,
            ),
            "repair_loop_id": repair_loop_manifest.get("repair_loop_id"),
            "instruction": (
                "Generate a repair proposal only. Do not commit, promote, or modify the live repository. "
                "Avoid repeating failed local repair approaches. Return a proposal compatible with patch staging."
            ),
        }

    def _summarize_attempts(self, attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []

        for attempt in attempts:
            summaries.append(
                {
                    "attempt_number": attempt.get("attempt_number"),
                    "source": attempt.get("source", "local"),
                    "repair_patch_id": attempt.get("repair_patch_id"),
                    "verification_id": attempt.get("verification_id"),
                    "validation_result": attempt.get("validation_result"),
                    "decision": attempt.get("decision"),
                    "changed_files": attempt.get("changed_files", []),
                    "reason": attempt.get("reason"),
                }
            )

        return summaries

    def _summarize_validation(
        self,
        report: dict[str, Any] | None,
        *,
        max_error_chars: int,
    ) -> dict[str, Any] | None:
        if not report:
            return None

        raw_errors = (
            report.get("error_output")
            or report.get("test_output")
            or report.get("stdout")
            or report.get("stderr")
            or report.get("reasoning")
            or ""
        )

        if isinstance(raw_errors, list):
            raw_errors = "\n".join(str(item) for item in raw_errors)

        return {
            "verification_id": report.get("verification_id"),
            "patch_id": report.get("patch_id"),
            "result": report.get("result") or report.get("status"),
            "summary": str(raw_errors)[:max_error_chars],
            "truncated": len(str(raw_errors)) > max_error_chars,
        }

    def _compact_evidence(
        self,
        evidence: dict[str, Any] | list[Any] | None,
        *,
        max_items: int,
    ) -> list[Any]:
        if evidence is None:
            return []

        if isinstance(evidence, list):
            return evidence[:max_items]

        if isinstance(evidence, dict):
            items = evidence.get("evidence") or evidence.get("items")
            if isinstance(items, list):
                return items[:max_items]

            return [
                {"key": key, "value": value}
                for key, value in list(evidence.items())[:max_items]
            ]

        return []