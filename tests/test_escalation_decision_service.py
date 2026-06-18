from pathlib import Path

from models.consultation import ConsultationType, EscalationDecisionAction
from models.work_packet import WorkPacket
from services.escalation_decision_service import EscalationDecisionService


def test_local_only_decision(tmp_path: Path):
    packet = WorkPacket(
        objective="Small grounded change",
        approved_scope=["services/foo.py"],
    )

    decision = EscalationDecisionService(tmp_path).decide(packet, planner_confidence=0.95)

    assert decision.action == EscalationDecisionAction.LOCAL_ONLY
    assert decision.reasons == ["deterministic_local_execution_allowed"]


def test_planning_escalation_decision_for_low_planner_confidence(tmp_path: Path):
    packet = WorkPacket(
        objective="Complex design change",
        approved_scope=["services/foo.py"],
    )

    decision = EscalationDecisionService(tmp_path).decide(packet, planner_confidence=0.42)

    assert decision.action == EscalationDecisionAction.CONSULTATION_REQUIRED
    assert decision.consultation_type == ConsultationType.ARCHITECTURE_REVIEW
    assert "planner_confidence_below_threshold" in decision.reasons


def test_repair_escalation_decision_for_validation_failure(tmp_path: Path):
    packet = WorkPacket(
        objective="Fix failed validation",
        approved_scope=["services/foo.py"],
    )

    decision = EscalationDecisionService(tmp_path).decide(packet, validation_failures=1)

    assert decision.action == EscalationDecisionAction.REPAIR_REQUIRED
    assert decision.consultation_type == ConsultationType.REPAIR_ANALYSIS
    assert "validation_failures_present" in decision.reasons


def test_unresolved_targets_block_consultation(tmp_path: Path):
    packet = WorkPacket(
        objective="Modify missing target",
        approved_scope=["services/foo.py"],
        unresolved_target_files=["services/nope.py"],
        planner_revisit_required=True,
    )

    decision = EscalationDecisionService(tmp_path).decide(packet, planner_confidence=0.1)

    assert decision.action == EscalationDecisionAction.HUMAN_REQUIRED
    assert decision.reasons == ["unresolved_targets_block_consultation"]
