from enum import Enum


class RepairOutcomeAction(str, Enum):
    HUMAN_REVIEW = "human_review"
    CONTINUE_REPAIR = "continue_repair"
    ESCALATE_REPAIR = "escalate_repair"


class RepairOutcomeService:
    def evaluate(
        self,
        validation_result: str,
        attempt_number: int,
        max_attempts: int,
    ) -> RepairOutcomeAction:
        normalized = validation_result.upper().strip()

        if normalized == "PASS":
            return RepairOutcomeAction.HUMAN_REVIEW

        if normalized in {"FAIL", "WARN"}:
            if attempt_number < max_attempts:
                return RepairOutcomeAction.CONTINUE_REPAIR
            return RepairOutcomeAction.ESCALATE_REPAIR

        return RepairOutcomeAction.HUMAN_REVIEW