from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models.validation_evidence import (
    ValidationEvidence,
    ValidationEvidenceResult,
    ValidationEvidenceViolation,
)
from services.requirement_trace_service import RequirementTrace, RequirementTraceResult
from services.behavioral_smoke_verifier import BehavioralSmokeResult


class ValidationEvidenceService:
    """Generates and validates requirement-connected validation evidence."""

    def generate(
        self,
        *,
        trace_result: RequirementTraceResult,
        behavior_result: BehavioralSmokeResult | None = None,
        verification_source: str = "behavioral_smoke_verifier",
    ) -> list[ValidationEvidence]:
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence: list[ValidationEvidence] = []
        behavior_status = self._normalize_behavior_status(behavior_result)

        for trace in trace_result.traces:
            for test in trace.test_evidence:
                test_identifier = self._test_identifier(test)
                evidence.append(
                    ValidationEvidence(
                        requirement_id=trace.requirement_id,
                        test_identifier=test_identifier,
                        status=behavior_status,
                        verification_source=verification_source,
                        timestamp=timestamp,
                        details=(
                            "Behavioral verification passed for requirement-connected test evidence."
                            if behavior_status == "PASS"
                            else "Behavioral verification did not pass for requirement-connected test evidence."
                        ),
                    )
                )

        return evidence

    def attach_validation_evidence(
        self,
        *,
        trace_result: RequirementTraceResult,
        validation_evidence: list[ValidationEvidence],
    ) -> RequirementTraceResult:
        evidence_by_requirement: dict[str, list[ValidationEvidence]] = {}
        for evidence in validation_evidence:
            evidence_by_requirement.setdefault(evidence.requirement_id, []).append(evidence)

        for trace in trace_result.traces:
            trace.validation_evidence = evidence_by_requirement.get(trace.requirement_id, [])

        return trace_result

    def validate(
        self,
        *,
        proposal: dict[str, Any],
        trace_result: RequirementTraceResult,
        behavior_result: BehavioralSmokeResult | None = None,
    ) -> ValidationEvidenceResult:
        generated = self.generate(
            trace_result=trace_result,
            behavior_result=behavior_result,
        )
        self.attach_validation_evidence(
            trace_result=trace_result,
            validation_evidence=generated,
        )

        violations = self.validate_coverage(
            proposal=proposal,
            traces=trace_result.traces,
        )

        return ValidationEvidenceResult(
            status="fail" if violations else "pass",
            validation_evidence=generated,
            violations=violations,
        )

    def validate_coverage(
        self,
        *,
        proposal: dict[str, Any],
        traces: list[RequirementTrace],
    ) -> list[ValidationEvidenceViolation]:
        violations: list[ValidationEvidenceViolation] = []

        for trace in traces:
            if trace.implementation_evidence and not trace.test_evidence:
                violations.append(
                    ValidationEvidenceViolation(
                        code="MISSING_TEST_EVIDENCE",
                        message="Requirement has implementation evidence but no mapped test evidence.",
                        requirement_id=trace.requirement_id,
                        expected=trace.requirement_text,
                        actual="<missing>",
                        instruction="Provide a test that validates the requirement and include trace evidence.",
                    )
                )

            if trace.test_evidence and not trace.validation_evidence:
                violations.append(
                    ValidationEvidenceViolation(
                        code="MISSING_VALIDATION_EVIDENCE",
                        message="Requirement has test evidence but no validation evidence.",
                        requirement_id=trace.requirement_id,
                        expected=trace.requirement_text,
                        actual="<missing>",
                        instruction="Attach validation evidence showing the mapped test was checked.",
                    )
                )

            for evidence in trace.validation_evidence:
                if evidence.status != "PASS":
                    violations.append(
                        ValidationEvidenceViolation(
                            code="FAILED_VALIDATION_EVIDENCE",
                            message="Requirement validation evidence did not pass.",
                            requirement_id=trace.requirement_id,
                            expected="PASS",
                            actual=evidence.status,
                            instruction="Fix the implementation or test so validation evidence passes.",
                        )
                    )

        mapped_tests = {
            evidence.file_path
            for trace in traces
            for evidence in trace.test_evidence
            if evidence.file_path
        }
        proposed_tests = self._proposal_test_paths(proposal)

        for test_path in sorted(proposed_tests - mapped_tests):
            violations.append(
                ValidationEvidenceViolation(
                    code="UNMAPPED_TEST_EVIDENCE",
                    message="Proposal contains a test file that is not mapped to any requirement trace.",
                    expected="Every proposed test maps to a requirement.",
                    actual=test_path,
                    instruction="Map each test to a requirement or remove unrelated test changes.",
                )
            )

        return violations

    def summarize(self, result: ValidationEvidenceResult) -> dict[str, Any]:
        violations_by_code: dict[str, int] = {}
        for violation in result.violations:
            violations_by_code[violation.code] = violations_by_code.get(violation.code, 0) + 1

        requirements = {
            evidence.requirement_id
            for evidence in result.validation_evidence
        }
        passed = [
            evidence
            for evidence in result.validation_evidence
            if evidence.status == "PASS"
        ]

        return {
            "status": result.status,
            "requirements": len(requirements),
            "evidence_count": len(result.validation_evidence),
            "passed": len(passed),
            "failed": len(result.validation_evidence) - len(passed),
            "missing_test_evidence": violations_by_code.get("MISSING_TEST_EVIDENCE", 0),
            "missing_validation_evidence": violations_by_code.get("MISSING_VALIDATION_EVIDENCE", 0),
            "failed_validation_evidence": violations_by_code.get("FAILED_VALIDATION_EVIDENCE", 0),
            "unmapped_test_evidence": violations_by_code.get("UNMAPPED_TEST_EVIDENCE", 0),
            "violations": [violation.model_dump() for violation in result.violations],
        }

    def _normalize_behavior_status(
        self,
        behavior_result: BehavioralSmokeResult | None,
    ) -> str:
        if behavior_result is None:
            return "UNKNOWN"
        return "PASS" if behavior_result.passed else "FAIL"

    def _test_identifier(self, evidence: Any) -> str:
        file_path = evidence.file_path or "<unknown-test>"
        if evidence.line_start is None:
            return file_path
        return f"{file_path}:{evidence.line_start}"

    def _proposal_test_paths(self, proposal: dict[str, Any]) -> set[str]:
        paths: set[str] = set()
        for change in proposal.get("changes", []):
            if not isinstance(change, dict):
                continue
            path = change.get("path")
            if isinstance(path, str) and self._is_test_path(path):
                paths.add(path)
        return paths

    def _is_test_path(self, path: str) -> bool:
        normalized = str(path).replace("\\", "/")
        return normalized.startswith("tests/") or normalized.split("/")[-1].startswith("test_")
