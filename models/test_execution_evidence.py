from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TestExecutionStatus(str, Enum):
    __test__ = False
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"


class TestExecutionEvidence(BaseModel):
    __test__ = False
    test_identifier: str
    status: TestExecutionStatus
    duration_seconds: float
    timestamp: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None


class TestExecutionViolation(BaseModel):
    __test__ = False
    code: Literal[
        "TEST_EXECUTION_FAILED",
        "TEST_NOT_FOUND",
        "TEST_TIMEOUT",
        "NO_RUNTIME_EVIDENCE",
    ]
    message: str
    test_identifier: str | None = None
    expected: str | None = None
    actual: str | None = None
    instruction: str | None = None


class TestExecutionResult(BaseModel):
    __test__ = False
    status: Literal["pass", "fail"]
    runtime_evidence: list[TestExecutionEvidence] = Field(default_factory=list)
    violations: list[TestExecutionViolation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"
