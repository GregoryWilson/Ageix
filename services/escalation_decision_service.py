from __future__ import annotations

from models.consultation import (
    ConsultationType,
    EscalationDecision,
    EscalationDecisionAction,
)
from models.work_packet import WorkPacket
from services.controls_service import ControlsService


class EscalationDecisionService:
    """Deterministic decisioning for local-only, consultation, repair, or human escalation."""

    def __init__(self, repo_root: str = ".") -> None:
        self.controls = ControlsService(repo_root).get_raw_config().get("consultation", {})

    def decide(
        self,
        work_packet: WorkPacket,
        *,
        planner_confidence: float | None = None,
        target_resolution_confidence: float | None = None,
        proposal_quality_failures: int = 0,
        validation_failures: int = 0,
        repair_attempts: int = 0,
        context_complexity: int = 0,
    ) -> EscalationDecision:
        if not self.controls.get("enabled", True):
            return EscalationDecision(
                action=EscalationDecisionAction.LOCAL_ONLY,
                reasons=["consultation_disabled"],
            )

        if work_packet.planner_revisit_required or work_packet.unresolved_target_files:
            return EscalationDecision(
                action=EscalationDecisionAction.HUMAN_REQUIRED,
                reasons=["unresolved_targets_block_consultation"],
                human_guidance_allowed=True,
            )

        approved_scope = work_packet.approved_scope or work_packet.approved_target_files
        if not approved_scope:
            return EscalationDecision(
                action=EscalationDecisionAction.LOCAL_ONLY,
                reasons=["approved_scope_empty"],
            )

        reasons: list[str] = []
        if planner_confidence is not None and planner_confidence < float(self.controls.get("planner_confidence_threshold", 0.70)):
            reasons.append("planner_confidence_below_threshold")
        if target_resolution_confidence is not None and target_resolution_confidence < float(self.controls.get("target_resolution_confidence_threshold", 0.85)):
            reasons.append("target_resolution_confidence_below_threshold")
        if proposal_quality_failures >= int(self.controls.get("proposal_quality_failure_threshold", 1)):
            reasons.append("proposal_quality_failures_present")
        if context_complexity >= int(self.controls.get("context_complexity_threshold", 10)):
            reasons.append("high_context_complexity")

        if validation_failures > 0 or repair_attempts > 0:
            repair_reasons = list(reasons)
            if validation_failures > 0:
                repair_reasons.append("validation_failures_present")
            if repair_attempts > 0:
                repair_reasons.append("repair_loop_history_present")
            return EscalationDecision(
                action=EscalationDecisionAction.REPAIR_REQUIRED,
                reasons=repair_reasons,
                consultation_type=ConsultationType.REPAIR_ANALYSIS,
            )

        if reasons:
            consultation_type = ConsultationType.ARCHITECTURE_REVIEW
            if proposal_quality_failures:
                consultation_type = ConsultationType.PLANNING_ANALYSIS
            return EscalationDecision(
                action=EscalationDecisionAction.CONSULTATION_REQUIRED,
                reasons=reasons,
                consultation_type=consultation_type,
            )

        return EscalationDecision(
            action=EscalationDecisionAction.LOCAL_ONLY,
            reasons=["deterministic_local_execution_allowed"],
        )
