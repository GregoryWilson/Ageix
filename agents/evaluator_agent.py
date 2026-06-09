from models.repair_analysis import RepairAnalysis
from models.verification_result import VerificationResult


def analyze_verification_failure(
    verification_result: VerificationResult,
) -> RepairAnalysis:
    if not verification_result.failed:
        raise ValueError(
            f"Cannot analyze repair for non-failed verification: "
            f"{verification_result.verification_id}"
        )

    failure_summary = verification_result.failure_summary.strip()

    relevant_evidence: list[str] = []

    if verification_result.test_output.strip():
        relevant_evidence.append(verification_result.test_output.strip()[-4000:])

    for reasoning_item in verification_result.evaluator_reasoning:
        if reasoning_item.strip():
            relevant_evidence.append(reasoning_item.strip())

    observed_failure = failure_summary or "Verification failed."

    likely_cause = (
        "The staged patch did not satisfy the validation command or test expectations."
    )

    recommended_repair_objective = (
        "Repair the staged patch so the validation command passes while preserving "
        "the original objective and avoiding unrelated changes."
    )

    return RepairAnalysis(
        patch_id=verification_result.patch_id,
        verification_id=verification_result.verification_id,
        observed_failure=observed_failure,
        likely_cause=likely_cause,
        relevant_evidence=relevant_evidence,
        recommended_repair_objective=recommended_repair_objective,
    )