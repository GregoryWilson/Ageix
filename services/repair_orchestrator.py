from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.evaluator_agent import analyze_verification_failure
from models.repair_decision import RepairDecision
from models.repair_work_order import build_repair_work_order
from models.verification_result import VerificationResult
from services.repair_decision_service import RepairDecisionService
from services.repair_loop_state import RepairLoopState


@dataclass(frozen=True)
class RepairOrchestrationResult:
    decision: RepairDecision
    repair_packet: dict[str, Any] | None = None


class RepairOrchestrator:
    def __init__(self) -> None:
        self.decision_service = RepairDecisionService()

    def evaluate_for_repair(
        self,
        verification_result: VerificationResult,
        repair_loop_state: RepairLoopState,
    ) -> RepairOrchestrationResult:
        decision = self.decision_service.decide(
            verification_result=verification_result,
            repair_loop_state=repair_loop_state,
        )

        if decision.action.value != "approve_repair":
            return RepairOrchestrationResult(
                decision=decision,
                repair_packet=None,
            )

        repair_analysis = analyze_verification_failure(verification_result)
        repair_work_order = build_repair_work_order(
            verification_result=verification_result,
            repair_analysis=repair_analysis,
        )

        repair_packet = repair_work_order.to_packet()

        repair_attempt_number = repair_loop_state.attempts + 1

        repair_loop_state.record_attempt(
            repair_patch_id=(
                f"pending_repair_{repair_attempt_number}_for_"
                f"{verification_result.patch_id}"
            ),
            metadata={
                "verification_id": verification_result.verification_id,
            },
        )

        return RepairOrchestrationResult(
            decision=decision,
            repair_packet=repair_packet,
        )