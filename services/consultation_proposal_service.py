from __future__ import annotations

from models.consultation import (
    ConsultationProposal,
    ConsultationType,
    EscalationDecision,
    EscalationDecisionAction,
)
from models.work_packet import WorkPacket
from services.controls_service import ControlsService
from services.evidence_dictionary_service import EvidenceDictionaryService
from services.token_estimation_service import TokenEstimationService


class ConsultationProposalService:
    """Builds human approval previews before any external consultation spend."""

    DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"

    def __init__(self, repo_root: str = ".") -> None:
        self.controls = ControlsService(repo_root).get_raw_config().get("consultation", {})
        self.evidence_dictionary_service = EvidenceDictionaryService()
        self.token_estimator = TokenEstimationService()

    def build_proposal(
        self,
        work_packet: WorkPacket,
        decision: EscalationDecision,
        *,
        target_model: str | None = None,
    ) -> ConsultationProposal:
        if decision.action == EscalationDecisionAction.HUMAN_REQUIRED:
            consultation_type = decision.consultation_type or ConsultationType.PLANNING_ANALYSIS
        else:
            consultation_type = decision.consultation_type or ConsultationType.ARCHITECTURE_REVIEW

        evidence_dictionary = self.evidence_dictionary_service.build_dictionary(work_packet)
        model = target_model or str(self.controls.get("default_model", self.DEFAULT_MODEL))
        max_output_tokens = int(self.controls.get("max_output_tokens", 1500))

        sections = {
            "role_charter": self._role_charter(consultation_type),
            "governance_rules": self._governance_rules(),
            "objective": work_packet.objective,
            "approved_scope": work_packet.approved_scope or work_packet.approved_target_files,
            "evidence_dictionary": evidence_dictionary.model_dump(),
            "request_schema": self._request_schema(consultation_type),
        }
        cached_sections = set()
        if self.controls.get("enable_prompt_caching", True):
            cached_sections = {"role_charter", "governance_rules", "request_schema"}

        token_estimate = self.token_estimator.build_estimate(
            sections=sections,
            max_output_tokens=max_output_tokens,
            cached_prefix_sections=cached_sections,
        )
        cost_estimate = self.token_estimator.estimate_cost(
            model=model,
            token_estimate=token_estimate,
        )

        return ConsultationProposal(
            consultation_type=consultation_type,
            target_model=model,
            reason_for_consultation=decision.reasons,
            expected_benefit=self._expected_benefit(consultation_type),
            impact_if_skipped=self._impact_if_skipped(consultation_type),
            requires_human_approval=bool(self.controls.get("require_human_approval", True)),
            human_guidance_allowed=bool(self.controls.get("allow_human_guidance", True)),
            approved_scope_summary=list(work_packet.approved_scope or work_packet.approved_target_files),
            token_estimate=token_estimate,
            cost_estimate=cost_estimate,
            evidence_dictionary=evidence_dictionary,
            governance={
                "repository_grounded": not bool(work_packet.unresolved_target_files),
                "scope_approved": bool(work_packet.approved_scope or work_packet.approved_target_files),
                "cloud_may_expand_scope": False,
                "cloud_may_modify_files": False,
                "approval_required_before_spend": bool(self.controls.get("require_human_approval", True)),
            },
        )

    def _role_charter(self, consultation_type: ConsultationType) -> str:
        return (
            f"You are participating as {consultation_type.value}. "
            "Return only the requested structured artifact. "
            "No praise, encouragement, narrative, or scope expansion."
        )

    def _governance_rules(self) -> list[str]:
        return [
            "Repository evidence is authoritative.",
            "Approved scope is authoritative.",
            "External participants are advisors only.",
            "External participants cannot approve scope or modify files.",
            "If evidence is insufficient, request specific evidence by evidence_id.",
        ]

    def _request_schema(self, consultation_type: ConsultationType) -> dict[str, list[str] | str]:
        if consultation_type == ConsultationType.REPAIR_ANALYSIS:
            return {
                "required_fields": ["likely_root_causes", "recommended_investigation_order", "evidence_requests"],
                "format": "json_only",
            }
        if consultation_type == ConsultationType.PLANNING_ANALYSIS:
            return {
                "required_fields": ["plan_gaps", "missing_tasks", "task_ordering_concerns", "evidence_requests"],
                "format": "json_only",
            }
        return {
            "required_fields": ["architectural_concerns", "governance_risks", "missing_tests", "evidence_requests"],
            "format": "json_only",
        }

    def _expected_benefit(self, consultation_type: ConsultationType) -> list[str]:
        if consultation_type == ConsultationType.REPAIR_ANALYSIS:
            return ["identify likely validation failure causes", "prioritize grounded investigation areas"]
        if consultation_type == ConsultationType.PLANNING_ANALYSIS:
            return ["identify missing implementation tasks", "challenge task ordering before DevWorker execution"]
        return ["independent architecture review", "identify governance risks", "identify missing validation coverage"]

    def _impact_if_skipped(self, consultation_type: ConsultationType) -> list[str]:
        if consultation_type == ConsultationType.REPAIR_ANALYSIS:
            return ["repair loop may repeat failed assumptions", "human review may be needed sooner"]
        if consultation_type == ConsultationType.PLANNING_ANALYSIS:
            return ["planner may miss decomposition gaps", "DevWorker may receive incomplete task scope"]
        return ["architectural risks may be discovered later", "implementation rework risk may increase"]
