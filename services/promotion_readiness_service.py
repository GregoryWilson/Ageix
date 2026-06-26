from __future__ import annotations

from pathlib import Path
from typing import Any

from models.promotion_readiness import PromotionBlocker, PromotionReadinessResult
from services.controls_service import ControlsService


class PromotionReadinessService:
    """Deterministically evaluates whether a candidate patch is ready for promotion."""

    REMEDIATION = {
        "LOW_CONFIDENCE": "Provide stronger validation evidence and improve implementation confidence.",
        "FAILED_RUNTIME_VALIDATION": "Investigate runtime validation failures and provide a corrected implementation.",
        "MISSING_TEST_COVERAGE": "Provide executable test coverage supporting the implementation.",
        "MISSING_REQUIREMENT_TRACE": "Add requirement trace evidence that maps requested behavior to implementation and tests.",
        "QUALITY_VALIDATION_FAILURE": "Correct proposal quality violations before requesting promotion.",
        "VALIDATION_EVIDENCE_FAILURE": "Provide complete validation evidence for each traced requirement.",
        "GOVERNANCE_POLICY_VIOLATION": "Adjust the promotion request to comply with configured governance controls.",
    }

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.controls = ControlsService(Path(repo_root)).promotion_governance

    def evaluate(
        self,
        *,
        proposal_quality: Any = None,
        requirement_trace: Any = None,
        behavior_verification: Any = None,
        validation_evidence: Any = None,
        runtime_validation: Any = None,
        confidence_summary: dict[str, Any] | None = None,
    ) -> PromotionReadinessResult:
        confidence_summary = confidence_summary or {}
        confidence = float(confidence_summary.get("overall_confidence", 0.0))
        blockers: list[PromotionBlocker] = []

        if not self._passed(proposal_quality):
            blockers.append(self._blocker("QUALITY_VALIDATION_FAILURE", "Proposal quality validation did not pass."))

        if not self._passed(requirement_trace):
            blockers.append(self._blocker("MISSING_REQUIREMENT_TRACE", "Requirement trace validation did not pass."))

        if self._missing_test_coverage(requirement_trace):
            blockers.append(self._blocker("MISSING_TEST_COVERAGE", "Requirement trace evidence is missing executable test coverage."))

        if not self._passed(runtime_validation):
            blockers.append(self._blocker("FAILED_RUNTIME_VALIDATION", "Runtime validation did not pass."))

        if not self._passed(validation_evidence):
            blockers.append(self._blocker("VALIDATION_EVIDENCE_FAILURE", "Validation evidence did not pass."))

        if confidence < self.controls.minimum_confidence:
            blockers.append(
                self._blocker(
                    "LOW_CONFIDENCE",
                    f"Confidence {confidence:.2f} is below required minimum {self.controls.minimum_confidence:.2f}.",
                )
            )

        if blockers and not self.controls.allow_promotion_with_blockers:
            blockers.append(self._blocker("GOVERNANCE_POLICY_VIOLATION", "Configured governance forbids promotion with blockers."))

        status = self._status_for_blockers(blockers)
        recommendation = self._recommendation_for_status(status)

        return PromotionReadinessResult(
            status=status,
            confidence=round(confidence, 4),
            blockers=blockers,
            recommendation=recommendation,
            human_approval_required=self.controls.human_approval_required,
        )

    def summarize(self, result: PromotionReadinessResult) -> dict[str, Any]:
        return {
            "status": result.status,
            "confidence": result.confidence,
            "blockers": [blocker.model_dump() for blocker in result.blockers],
            "recommendation": result.recommendation,
            "human_approval_required": result.human_approval_required,
        }

    def _blocker(self, code: str, message: str) -> PromotionBlocker:
        return PromotionBlocker(
            code=code,  # type: ignore[arg-type]
            severity="critical" if code == "GOVERNANCE_POLICY_VIOLATION" else "error",
            message=message,
            remediation=self.REMEDIATION[code],
        )

    def _status_for_blockers(self, blockers: list[PromotionBlocker]) -> str:
        if not blockers:
            return "ready"
        if self.controls.allow_promotion_with_blockers:
            return "conditional"
        return "blocked"

    def _recommendation_for_status(self, status: str) -> str:
        if status == "ready":
            return "promote"
        if status == "conditional":
            return "review"
        return "reject"

    def _passed(self, value: Any) -> bool:
        if value is None:
            return False
        passed = getattr(value, "passed", None)
        if isinstance(passed, bool):
            return passed
        if isinstance(value, dict):
            status = value.get("status")
            if status is None and isinstance(value.get("summary"), dict):
                status = value["summary"].get("status")
            return str(status).lower() in {"pass", "passed", "ready"}
        status = getattr(value, "status", None)
        return str(status).lower() in {"pass", "passed", "ready"}

    def _missing_test_coverage(self, requirement_trace: Any) -> bool:
        if requirement_trace is None:
            return True
        if hasattr(requirement_trace, "traces"):
            traces = requirement_trace.traces
            return any(
                self._trace_requires_test_evidence(trace)
                and not getattr(trace, "test_evidence", [])
                for trace in traces
            )
        if isinstance(requirement_trace, dict):
            traces = requirement_trace.get("traces", [])
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                if self._trace_requires_test_evidence(trace) and not trace.get("test_evidence", []):
                    return True
        return False

    def _trace_requires_test_evidence(self, trace: Any) -> bool:
        if isinstance(trace, dict):
            text = str(trace.get("requirement_text", "")).lower()
        else:
            text = str(getattr(trace, "requirement_text", "")).lower()

        # File-existence criteria for implementation files are satisfied by the
        # implementation evidence itself. Requiring test_evidence here causes
        # promotion readiness to disagree with RequirementTraceService and
        # ValidationEvidenceService.
        if any(
            marker in text
            for marker in (
                "authorized target file exists",
                "target file exists",
                "file exists in proposal",
            )
        ):
            return "tests/" in text or "test_" in text

        # Meta criteria are evaluated by the trace and validation evidence
        # services rather than direct test evidence on the meta trace itself.
        if "requirement trace covers" in text:
            return False

        return any(
            marker in text
            for marker in (
                "test",
                "pytest",
                "unit test",
                "generated test command passes",
                "executable test target",
            )
        )
