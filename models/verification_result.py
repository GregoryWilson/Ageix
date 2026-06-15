from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class VerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class VerificationResult:
    verification_id: str
    patch_id: str
    status: VerificationStatus
    failure_summary: str
    evaluator_reasoning: list[str] = field(default_factory=list)
    test_output: str = ""
    report_path: Path | None = None
    test_output_path: Path | None = None
    raw_report: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == VerificationStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status == VerificationStatus.FAIL

    @property
    def warned(self) -> bool:
        return self.status == VerificationStatus.WARN