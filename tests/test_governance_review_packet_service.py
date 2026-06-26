from pathlib import Path

from services.governance_review_packet_service import GovernanceReviewPacketService
from services.promotion_readiness_service import PromotionReadinessService
from services.staging_service import StagingService


class PassingResult:
    status = "pass"

    @property
    def passed(self):
        return True


class Trace:
    test_evidence = ["tests/test_example.py"]


class TraceResult:
    status = "pass"
    traces = [Trace()]

    @property
    def passed(self):
        return True


def _ready_result(tmp_path: Path):
    return PromotionReadinessService(tmp_path).evaluate(
        proposal_quality=PassingResult(),
        requirement_trace=TraceResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_validation=PassingResult(),
        confidence_summary={"overall_confidence": 0.93},
    )


def test_governance_review_packet_generation(tmp_path: Path):
    packet = GovernanceReviewPacketService().build_packet(
        objective="Add promotion readiness",
        implementation_summary="Adds deterministic promotion review.",
        changed_files=["services/promotion_readiness_service.py"],
        requirement_trace={"traces": [{"requirement_id": "REQ-001"}]},
        behavior_verification={"status": "pass"},
        validation_evidence={"status": "pass"},
        runtime_evidence={"status": "pass"},
        confidence_summary={"overall_confidence": 0.93},
        promotion_readiness=_ready_result(tmp_path),
    )

    assert packet.objective == "Add promotion readiness"
    assert packet.changed_files == ["services/promotion_readiness_service.py"]
    assert packet.requirement_traces[0]["requirement_id"] == "REQ-001"
    assert packet.promotion_recommendation == "promote"


def test_manifest_contains_promotion_summary(tmp_path: Path):
    (tmp_path / "example.py").write_text("VALUE = 1\n", encoding="utf-8")

    manifest = StagingService(tmp_path).create_stage(
        files=["example.py"],
        summary="promotion manifest test",
        confidence_summary={"overall_confidence": 0.93},
        promotion_readiness_summary={
            "status": "ready",
            "confidence": 0.93,
            "blockers": [],
            "recommendation": "promote",
        },
        governance_review_packet={"generated": True, "recommendation": "promote"},
    )

    data = manifest.to_dict()
    assert data["promotion_readiness_summary"]["status"] == "ready"
    assert data["governance_review_packet"]["generated"] is True
