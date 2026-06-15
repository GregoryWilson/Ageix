from pathlib import Path

from pydantic import BaseModel

from services.promotion_readiness_service import PromotionReadinessService


class PassingResult(BaseModel):
    status: str = "pass"

    @property
    def passed(self):
        return True


class FailingResult(BaseModel):
    status: str = "fail"

    @property
    def passed(self):
        return False


class Trace(BaseModel):
    test_evidence: list[str] = ["tests/test_example.py"]


class TraceResult(BaseModel):
    status: str = "pass"
    traces: list[Trace] = [Trace()]

    @property
    def passed(self):
        return True


class MissingTraceCoverageResult(BaseModel):
    status: str = "pass"
    traces: list[Trace] = [Trace(test_evidence=[])]

    @property
    def passed(self):
        return True


def test_promotion_readiness_ready(tmp_path: Path):
    result = PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=TraceResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=PassingResult(),
        confidence_summary={"overall_confidence": 0.93},
    )

    assert result.status == "ready"
    assert result.recommendation == "promote"
    assert result.blockers == []
    assert result.passed is True


def test_promotion_readiness_low_confidence(tmp_path: Path):
    result = PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=TraceResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=PassingResult(),
        confidence_summary={"overall_confidence": 0.60},
    )

    codes = [blocker.code for blocker in result.blockers]
    assert result.status == "blocked"
    assert result.recommendation == "reject"
    assert "LOW_CONFIDENCE" in codes
    assert "GOVERNANCE_POLICY_VIOLATION" in codes


def test_promotion_readiness_detects_runtime_failure(tmp_path: Path):
    result = PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=TraceResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=FailingResult(),
        confidence_summary={"overall_confidence": 0.90},
    )

    codes = [blocker.code for blocker in result.blockers]
    assert "FAILED_RUNTIME_VALIDATION" in codes
    assert result.status == "blocked"


def test_promotion_readiness_detects_missing_traceability(tmp_path: Path):
    result = PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=FailingResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=PassingResult(),
        confidence_summary={"overall_confidence": 0.90},
    )

    codes = [blocker.code for blocker in result.blockers]
    assert "MISSING_REQUIREMENT_TRACE" in codes
    assert result.status == "blocked"


def test_promotion_readiness_detects_missing_test_coverage(tmp_path: Path):
    result = PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=MissingTraceCoverageResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=PassingResult(),
        confidence_summary={"overall_confidence": 0.90},
    )

    codes = [blocker.code for blocker in result.blockers]
    assert "MISSING_TEST_COVERAGE" in codes
