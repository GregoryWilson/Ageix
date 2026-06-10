from services.repair_outcome_service import (
    RepairOutcomeAction,
    RepairOutcomeService,
)


def test_pass_routes_to_human_review():
    service = RepairOutcomeService()

    result = service.evaluate(
        validation_result="PASS",
        attempt_number=1,
        max_attempts=3,
    )

    assert result == RepairOutcomeAction.HUMAN_REVIEW


def test_fail_with_attempts_remaining_continues_repair():
    service = RepairOutcomeService()

    result = service.evaluate(
        validation_result="FAIL",
        attempt_number=1,
        max_attempts=3,
    )

    assert result == RepairOutcomeAction.CONTINUE_REPAIR


def test_warn_with_attempts_remaining_continues_repair():
    service = RepairOutcomeService()

    result = service.evaluate(
        validation_result="WARN",
        attempt_number=1,
        max_attempts=3,
    )

    assert result == RepairOutcomeAction.CONTINUE_REPAIR


def test_fail_at_attempt_limit_escalates():
    service = RepairOutcomeService()

    result = service.evaluate(
        validation_result="FAIL",
        attempt_number=3,
        max_attempts=3,
    )

    assert result == RepairOutcomeAction.ESCALATE_REPAIR


def test_warn_at_attempt_limit_escalates():
    service = RepairOutcomeService()

    result = service.evaluate(
        validation_result="WARN",
        attempt_number=3,
        max_attempts=3,
    )

    assert result == RepairOutcomeAction.ESCALATE_REPAIR