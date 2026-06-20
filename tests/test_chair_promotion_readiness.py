from chair import build_promotion_retry_packet
from services.promotion_readiness_service import PromotionReadinessService


class PassingResult:
    status = "pass"

    @property
    def passed(self):
        return True


class FailingResult:
    status = "fail"

    @property
    def passed(self):
        return False


class Trace:
    test_evidence = ["tests/test_example.py"]


class TraceResult:
    status = "pass"
    traces = [Trace()]

    @property
    def passed(self):
        return True


def test_chair_rejects_blocked_promotion_candidate(tmp_path):
    readiness = PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=TraceResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=FailingResult(),
        confidence_summary={"overall_confidence": 0.90},
    )

    packet = build_promotion_retry_packet(
        devworker_packet={"constraints": {}},
        promotion_readiness=readiness,
    )

    assert readiness.status == "blocked"
    assert readiness.recommendation == "reject"
    assert packet["promotion_readiness_retry"] is True
    assert "Investigate runtime validation failures" in packet["promotion_readiness_feedback"]
    assert packet["constraints"]["promotion_readiness_retry"] is True
