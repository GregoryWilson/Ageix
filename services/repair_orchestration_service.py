from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


MAX_REPAIR_ATTEMPTS = 3


class RepairDecisionAction(str, Enum):
    APPROVE_REPAIR = "APPROVE_REPAIR"
    REQUEST_HUMAN_REVIEW = "REQUEST_HUMAN_REVIEW"


@dataclass(frozen=True)
class RepairDecision:
    action: RepairDecisionAction
    approved: bool
    patch_id: str | None
    verification_id: str | None
    attempt_number: int
    max_attempts: int
    reason: str
    reasoning: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


@dataclass(frozen=True)
class RepairWorkOrder:
    work_order_type: str
    patch_id: str
    source_verification_id: str
    attempt_number: int
    objective: str | None
    repair_objective: str
    failure_reason: str
    verification_result: str
    decision: dict[str, Any]
    required_next_step: str
    safety_constraints: list[str]
    changed_files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepairOrchestrationService:
    def evaluate_repair_decision(
        self,
        verification: dict[str, Any],
    ) -> RepairDecision:
        result = str(verification.get("result", "")).upper()
        patch_id = verification.get("patch_id")
        verification_id = verification.get("verification_id")
        attempt_number = self.next_attempt_number(verification)

        if result == "PASS":
            return RepairDecision(
                action=RepairDecisionAction.REQUEST_HUMAN_REVIEW,
                approved=False,
                patch_id=patch_id,
                verification_id=verification_id,
                attempt_number=attempt_number,
                max_attempts=MAX_REPAIR_ATTEMPTS,
                reason="verification_passed",
                reasoning=[
                    "Verification passed; repair is not required.",
                    "Patch should proceed to human review before promotion.",
                ],
            )

        if result not in {"FAIL", "WARN"}:
            return RepairDecision(
                action=RepairDecisionAction.REQUEST_HUMAN_REVIEW,
                approved=False,
                patch_id=patch_id,
                verification_id=verification_id,
                attempt_number=attempt_number,
                max_attempts=MAX_REPAIR_ATTEMPTS,
                reason="unsupported_verification_result",
                reasoning=[
                    f"Verification result '{result}' is not eligible for automated repair."
                ],
            )

        if attempt_number > MAX_REPAIR_ATTEMPTS:
            return RepairDecision(
                action=RepairDecisionAction.REQUEST_HUMAN_REVIEW,
                approved=False,
                patch_id=patch_id,
                verification_id=verification_id,
                attempt_number=attempt_number,
                max_attempts=MAX_REPAIR_ATTEMPTS,
                reason="repair_attempt_limit_reached",
                reasoning=[
                    (
                        f"Repair attempt {attempt_number} would exceed "
                        f"max attempts of {MAX_REPAIR_ATTEMPTS}."
                    )
                ],
            )

        return RepairDecision(
            action=RepairDecisionAction.APPROVE_REPAIR,
            approved=True,
            patch_id=patch_id,
            verification_id=verification_id,
            attempt_number=attempt_number,
            max_attempts=MAX_REPAIR_ATTEMPTS,
            reason="verification_failed_repair_allowed",
            reasoning=[
                f"Verification result is {result}.",
                "Repair attempt limit has not been reached.",
                "Repair work order may be generated.",
            ],
        )

    def build_repair_work_order(
        self,
        verification: dict[str, Any],
        decision: RepairDecision,
    ) -> RepairWorkOrder:
        if not verification.get("patch_id"):
            raise ValueError("Cannot build repair work order without patch_id.")

        if not verification.get("verification_id"):
            raise ValueError("Cannot build repair work order without verification_id.")

        failure_reason = self.extract_failure_reason(verification)
        changed_files = self.extract_changed_files(verification)

        return RepairWorkOrder(
            work_order_type="repair",
            patch_id=str(verification["patch_id"]),
            source_verification_id=str(verification["verification_id"]),
            attempt_number=decision.attempt_number,
            objective=verification.get("objective"),
            repair_objective=(
                "Repair the staged patch so validation passes without changing "
                "the original intent of the patch."
            ),
            failure_reason=failure_reason,
            verification_result=str(verification.get("result", "")),
            decision=decision.to_dict(),
            required_next_step="repository_evidence_collection",
            safety_constraints=[
                "Do not promote patches.",
                "Do not commit patches.",
                "Do not bypass validation.",
                "Do not exceed max repair attempts.",
                "Preserve the original patch objective.",
            ],
            changed_files=changed_files,
        )

    def next_attempt_number(self, verification: dict[str, Any]) -> int:
        existing_attempt = verification.get("repair_attempt")

        if isinstance(existing_attempt, int):
            return existing_attempt + 1

        metadata = verification.get("metadata")
        if isinstance(metadata, dict):
            metadata_attempt = metadata.get("repair_attempt")
            if isinstance(metadata_attempt, int):
                return metadata_attempt + 1

        return 1

    def extract_failure_reason(self, verification: dict[str, Any]) -> str:
        errors = verification.get("errors")
        if isinstance(errors, list) and errors:
            return "\n".join(str(error) for error in errors)

        reasoning = verification.get("reasoning")
        if isinstance(reasoning, list) and reasoning:
            return "\n".join(str(item) for item in reasoning)

        return str(
            verification.get("reason")
            or verification.get("summary")
            or "Verification did not pass."
        )
    
    
    def extract_changed_files(self, verification: dict[str, Any]) -> list[str]:
        changed_files = verification.get("changed_files")
        if isinstance(changed_files, list):
            return [str(path) for path in changed_files if isinstance(path, str)]

        patch_manifest = verification.get("patch_manifest")
        if isinstance(patch_manifest, dict):
            manifest_files = patch_manifest.get("changed_files")
            if isinstance(manifest_files, list):
                return [str(path) for path in manifest_files if isinstance(path, str)]

        return []