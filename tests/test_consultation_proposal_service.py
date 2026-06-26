from pathlib import Path

from models.consultation import ConsultationType, EscalationDecision, EscalationDecisionAction
from models.work_packet import WorkPacket
from services.consultation_proposal_service import ConsultationProposalService


def test_consultation_proposal_requires_human_approval(tmp_path: Path):
    packet = WorkPacket(
        objective="Add consultation governance",
        approved_scope=["services/consultation_proposal_service.py"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["planner_confidence_below_threshold"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )

    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)

    assert proposal.requires_human_approval is True
    assert proposal.governance["approval_required_before_spend"] is True
    assert "provide_human_guidance" in proposal.options


def test_consultation_proposal_estimates_tokens_and_cost(tmp_path: Path):
    packet = WorkPacket(
        objective="Add consultation governance",
        approved_scope=["services/consultation_proposal_service.py"],
        repository_evidence=["services/controls_service.py"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["high_context_complexity"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )

    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)

    assert proposal.token_estimate.estimated_input_tokens > 0
    assert proposal.token_estimate.estimated_output_tokens == 1500
    assert proposal.cost_estimate is not None
    assert proposal.cost_estimate.estimated_total_cost > 0


def test_consultation_proposal_includes_skip_impact_and_expected_benefit(tmp_path: Path):
    packet = WorkPacket(
        objective="Review architecture",
        approved_scope=["services/foo.py"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["high_context_complexity"],
        consultation_type=ConsultationType.ARCHITECTURE_REVIEW,
    )

    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)

    assert "independent architecture review" in proposal.expected_benefit
    assert "architectural risks may be discovered later" in proposal.impact_if_skipped


def test_consultation_proposal_contains_evidence_dictionary(tmp_path: Path):
    packet = WorkPacket(
        objective="Review architecture",
        approved_scope=["services/foo.py"],
        acceptance_criteria=["No cloud spend without approval"],
    )
    decision = EscalationDecision(
        action=EscalationDecisionAction.CONSULTATION_REQUIRED,
        reasons=["high_context_complexity"],
        consultation_type=ConsultationType.PLANNING_ANALYSIS,
    )

    proposal = ConsultationProposalService(tmp_path).build_proposal(packet, decision)

    assert proposal.evidence_dictionary is not None
    assert proposal.evidence_dictionary.items
    assert proposal.consultation_type == ConsultationType.PLANNING_ANALYSIS
    assert proposal.governance["cloud_may_expand_scope"] is False
