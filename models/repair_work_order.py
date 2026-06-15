from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.repair_analysis import RepairAnalysis
from models.verification_result import VerificationResult


@dataclass(frozen=True)
class RepairWorkOrder:
    work_type: str
    patch_id: str
    verification_id: str
    failure_reason: str
    repair_objective: str
    evidence: list[str] = field(default_factory=list)
    original_objective: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_packet(self) -> dict[str, Any]:
        return {
            "work_type": self.work_type,
            "patch_id": self.patch_id,
            "verification_id": self.verification_id,
            "failure_reason": self.failure_reason,
            "repair_objective": self.repair_objective,
            "evidence": self.evidence,
            "original_objective": self.original_objective,
            "metadata": self.metadata,
        }


def build_repair_work_order(
    verification_result: VerificationResult,
    repair_analysis: RepairAnalysis,
) -> RepairWorkOrder:
    raw_manifest = verification_result.raw_report.get("patch_manifest", {})
    original_objective = ""

    if isinstance(raw_manifest, dict):
        original_objective = str(raw_manifest.get("objective", ""))

    return RepairWorkOrder(
        work_type="repair",
        patch_id=verification_result.patch_id,
        verification_id=verification_result.verification_id,
        failure_reason=repair_analysis.observed_failure,
        repair_objective=repair_analysis.recommended_repair_objective,
        evidence=repair_analysis.relevant_evidence,
        original_objective=original_objective,
        metadata={
            "likely_cause": repair_analysis.likely_cause,
            "source": "evaluator",
        },
    )