from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RepairIntelligenceService:
    """Records and summarizes Ageix repair intelligence artifacts.

    This service is intentionally artifact-only. It does not mutate repository
    source files, run tests, promote patches, or commit changes.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "repair_intelligence"
        self.outcomes_root = self.root / "outcomes"
        self.metrics_path = self.root / "metrics.json"

    def record_repair_outcome(
        self,
        patch_id: str,
        result: str,
        files_modified: list[str] | None = None,
        repair_attempts: int = 0,
        cloud_escalations: int = 0,
        failure_type: str | None = None,
        successful_strategy: str | None = None,
        lineage_id: str | None = None,
        verification_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_result = result.upper()
        if normalized_result not in {"PASS", "FAIL"}:
            raise ValueError("result must be PASS or FAIL")

        artifact = {
            "patch_id": patch_id,
            "result": normalized_result,
            "repair_attempts": repair_attempts,
            "cloud_escalations": cloud_escalations,
            "files_modified": files_modified or [],
            "failure_type": failure_type,
            "successful_strategy": successful_strategy,
            "lineage_id": lineage_id,
            "verification_id": verification_id,
            "metadata": metadata or {},
            "timestamp": self._now(),
        }

        self._write_json(self._outcome_path(patch_id), artifact)
        self._write_json(self.metrics_path, self.get_patch_statistics())
        return artifact

    def record_verification_outcome(
        self,
        patch_id: str,
        verification_id: str,
        result: str,
        files_modified: list[str] | None = None,
        failure_type: str | None = "validation_failure",
    ) -> dict[str, Any]:
        return self.record_repair_outcome(
            patch_id=patch_id,
            verification_id=verification_id,
            result=result,
            files_modified=files_modified,
            failure_type=None if result.upper() == "PASS" else failure_type,
        )

    def record_cloud_escalation(
        self,
        patch_id: str,
        result: str,
        files_modified: list[str] | None = None,
        repair_attempts: int = 0,
        failure_type: str | None = None,
    ) -> dict[str, Any]:
        return self.record_repair_outcome(
            patch_id=patch_id,
            result=result,
            files_modified=files_modified,
            repair_attempts=repair_attempts,
            cloud_escalations=1,
            failure_type=failure_type,
            successful_strategy="cloud_escalation" if result.upper() == "PASS" else None,
        )

    def record_commit_success(
        self,
        patch_id: str,
        commit_record_id: str,
        git_commit: str,
        files_modified: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.record_repair_outcome(
            patch_id=patch_id,
            result="PASS",
            files_modified=files_modified,
            successful_strategy="human_commit",
            metadata={
                "commit_record_id": commit_record_id,
                "git_commit": git_commit,
            },
        )

    def get_patch_statistics(self) -> dict[str, Any]:
        outcomes = self._load_outcomes()
        total = len(outcomes)
        successes = [o for o in outcomes if o.get("result") == "PASS"]
        failures = [o for o in outcomes if o.get("result") == "FAIL"]
        cloud = [o for o in outcomes if int(o.get("cloud_escalations") or 0) > 0]
        cloud_successes = [o for o in cloud if o.get("result") == "PASS"]

        successful_attempt_counts = [int(o.get("repair_attempts") or 0) for o in successes]

        return {
            "total_repairs": total,
            "successful_repairs": len(successes),
            "failed_repairs": len(failures),
            "cloud_escalations": len(cloud),
            "cloud_escalation_success_rate": self._ratio(len(cloud_successes), len(cloud)),
            "average_attempts_before_success": self._average(successful_attempt_counts),
            "failure_patterns": self.get_failure_patterns(),
            "success_patterns": self.get_success_patterns(),
            "hotspots": self.get_hotspots(),
            "updated_at": self._now(),
        }

    def get_failure_patterns(self) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for outcome in self._load_outcomes():
            if outcome.get("result") == "FAIL":
                counter[outcome.get("failure_type") or "unknown"] += 1
        return dict(counter.most_common())

    def get_success_patterns(self) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for outcome in self._load_outcomes():
            if outcome.get("result") == "PASS":
                counter[outcome.get("successful_strategy") or "unknown"] += 1
        return dict(counter.most_common())

    def get_hotspots(self) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for outcome in self._load_outcomes():
            for path in outcome.get("files_modified", []):
                counter[path] += 1
        return dict(counter.most_common())

    def explain_failure_pattern(self, file_path: str) -> str:
        related = [
            outcome
            for outcome in self._load_outcomes()
            if file_path in outcome.get("files_modified", [])
        ]

        if not related:
            return f"{file_path} has no recorded repair intelligence."

        successes = [o for o in related if o.get("result") == "PASS"]
        failures = [o for o in related if o.get("result") == "FAIL"]
        failure_types = Counter(o.get("failure_type") or "unknown" for o in failures)
        success_strategies = Counter(o.get("successful_strategy") or "unknown" for o in successes)

        most_common_failure = failure_types.most_common(1)[0][0] if failure_types else "none"
        most_common_strategy = success_strategies.most_common(1)[0][0] if success_strategies else "none"

        return (
            f"{file_path} has participated in {len(related)} repairs.\n"
            f"Successful repairs: {len(successes)}.\n"
            f"Failed repairs: {len(failures)}.\n"
            f"Most common failure: {most_common_failure}.\n"
            f"Most common successful strategy: {most_common_strategy}."
        )

    def _outcome_path(self, patch_id: str) -> Path:
        return self.outcomes_root / patch_id / "repair_intelligence.json"

    def _load_outcomes(self) -> list[dict[str, Any]]:
        if not self.outcomes_root.exists():
            return []

        outcomes: list[dict[str, Any]] = []
        for path in self.outcomes_root.glob("*/repair_intelligence.json"):
            try:
                outcomes.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return outcomes

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ratio(self, numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _average(self, values: list[int]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)
