from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from models.dependency_intelligence import DependencyValidationEvidence


class ProposalQualityFailureCode(str, Enum):
    REQUIRED_LITERAL_MISSING = "required_literal_missing"
    UNAUTHORIZED_FILE_CHANGE = "unauthorized_file_change"
    REQUIRED_TARGET_FILE_MISSING = "required_target_file_missing"
    PYTHON_SYNTAX_ERROR = "python_syntax_error"
    TEST_WITHOUT_ASSERTION = "test_without_assertion"
    PLACEHOLDER_CONTENT = "placeholder_content"
    SUCCESS_CRITERIA_NOT_ADDRESSED = "success_criteria_not_addressed"
    UNSUPPORTED_DEPENDENCY_REFERENCE = "unsupported_dependency_reference"
    UNVERIFIED_EXTERNAL_API_USAGE = "unverified_external_api_usage"


class ProposalQualityViolation(BaseModel):
    code: ProposalQualityFailureCode
    message: str
    file_path: str | None = None
    expected: str | None = None
    actual: str | None = None
    retryable: bool = True
    instruction: str | None = None


class RequirementTrace(BaseModel):
    criterion: str
    implementation_evidence: list[str] = Field(default_factory=list)
    test_evidence: list[str] = Field(default_factory=list)


class ProposalQualityResult(BaseModel):
    status: Literal["pass", "fail"]
    violations: list[ProposalQualityViolation] = Field(default_factory=list)
    requirement_trace: list[RequirementTrace] = Field(default_factory=list)
    dependency_evidence: list[DependencyValidationEvidence] = Field(default_factory=list)
    research_required: bool = False
    escalation_recommended: bool = False
    escalation: dict = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def retryable(self) -> bool:
        return bool(self.violations) and all(
            violation.retryable for violation in self.violations
        )

    def to_feedback(self) -> str:
        if self.passed:
            return "Proposal quality validation passed."

        lines = ["Previous proposal failed deterministic quality validation."]
        for violation in self.violations:
            lines.append(f"- {violation.code.value}: {violation.message}")
            if violation.expected is not None:
                lines.append(f"  Expected: {violation.expected}")
            if violation.actual is not None:
                lines.append(f"  Actual: {violation.actual}")
            if violation.instruction is not None:
                lines.append(f"  Instruction: {violation.instruction}")

        lines.append("Revise the proposal to satisfy the original objective and success criteria exactly.")
        return "\n".join(lines)
