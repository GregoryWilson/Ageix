from pathlib import Path

from services.confidence_scoring_service import ConfidenceScoringService
from services.staging_service import StagingService


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


def test_confidence_summary_generated(tmp_path: Path):
    summary = ConfidenceScoringService(tmp_path).summarize(
        proposal_quality=PassingResult(),
        requirement_trace=PassingResult(),
        behavior_verification=PassingResult(),
        validation_evidence=PassingResult(),
        runtime_execution=FailingResult(),
    )

    assert summary["overall_confidence"] == 0.8
    assert summary["meets_minimum"] is True
    assert summary["components"]["runtime_execution"] == 0.0


def test_manifest_contains_runtime_summary(tmp_path: Path):
    (tmp_path / "example.py").write_text("VALUE = 1\n", encoding="utf-8")

    manifest = StagingService(tmp_path).create_stage(
        files=["example.py"],
        summary="runtime manifest test",
        runtime_validation_summary={
            "tests_executed": 1,
            "tests_passed": 1,
            "tests_failed": 0,
            "tests_timed_out": 0,
        },
        runtime_execution_evidence={"runtime_evidence": []},
        confidence_summary={"overall_confidence": 1.0},
    )

    data = manifest.to_dict()
    assert data["runtime_validation_summary"]["tests_executed"] == 1
    assert data["confidence_summary"]["overall_confidence"] == 1.0
