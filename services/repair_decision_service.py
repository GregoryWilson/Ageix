from __future__ import annotations

from models.repair_decision import RepairDecision, RepairDecisionAction
from models.verification_result import VerificationResult
from services.repair_loop_state import RepairLoopState


class RepairDecisionService:
    def decide(
        self,
        verification_result: VerificationResult,
        repair_loop_state: RepairLoopState,
    ) -> RepairDecision:
        if verification_result.passed:
            return RepairDecision(
                action=RepairDecisionAction.REQUEST_HUMAN_REVIEW,
                reasoning="Verification passed. Repair loop is complete and awaiting human review.",
            )

        if verification_result.warned:
            return RepairDecision(
                action=RepairDecisionAction.REQUEST_HUMAN_REVIEW,
                reasoning="Verification produced warnings. Human review is required before continuing.",
            )

        if not repair_loop_state.can_attempt_repair:
            return RepairDecision(
                action=RepairDecisionAction.REQUEST_HUMAN_REVIEW,
                reasoning="Repair attempt limit reached. Escalating to human review.",
            )

        return RepairDecision(
            action=RepairDecisionAction.APPROVE_REPAIR,
            reasoning="Verification failed and repair attempts remain available.",
        )