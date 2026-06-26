from models.consultation_recommendation import ConsultationDisposition
from models.participant_response import ParticipantResponse
from services.consultation_result_aggregator import ConsultationResultAggregator


def _response(participant_id: str, confidence: float, disposition: ConsultationDisposition):
    return ParticipantResponse(
        participant_id=participant_id,
        recommendation=f"{participant_id} recommendation",
        confidence=confidence,
        disposition=disposition,
        evidence_sufficient=disposition not in {ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE},
    )


def test_aggregate_single_response():
    recommendation = ConsultationResultAggregator().aggregate([
        _response("stub_architect", 0.8, ConsultationDisposition.PROCEED)
    ])

    assert recommendation.participant_count == 1
    assert recommendation.consensus == ConsultationDisposition.PROCEED


def test_aggregate_multiple_responses():
    recommendation = ConsultationResultAggregator().aggregate([
        _response("stub_architect", 0.8, ConsultationDisposition.PROCEED),
        _response("stub_code_reviewer", 0.6, ConsultationDisposition.PROCEED),
    ])

    assert recommendation.participant_count == 2
    assert recommendation.participant_ids == ["stub_architect", "stub_code_reviewer"]


def test_aggregate_confidence():
    recommendation = ConsultationResultAggregator().aggregate([
        _response("a", 0.8, ConsultationDisposition.PROCEED),
        _response("b", 0.6, ConsultationDisposition.PROCEED),
    ])

    assert recommendation.aggregate_confidence == 0.7


def test_detect_consensus():
    recommendation = ConsultationResultAggregator().aggregate([
        _response("a", 0.8, ConsultationDisposition.PROCEED),
        _response("b", 0.7, ConsultationDisposition.PROCEED_WITH_RECOMMENDATIONS),
    ])

    assert recommendation.consensus == ConsultationDisposition.PROCEED_WITH_RECOMMENDATIONS
    assert not recommendation.disagreement_detected


def test_detect_disagreement():
    recommendation = ConsultationResultAggregator().aggregate([
        _response("a", 0.8, ConsultationDisposition.PROCEED),
        _response("b", 0.7, ConsultationDisposition.CAUTION),
    ])

    assert recommendation.consensus == ConsultationDisposition.DISAGREEMENT
    assert recommendation.disagreement_detected


def test_blocked_insufficient_evidence_wins():
    recommendation = ConsultationResultAggregator().aggregate([
        _response("a", 0.8, ConsultationDisposition.PROCEED),
        _response("b", 0.2, ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE),
    ])

    assert recommendation.consensus == ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE
    assert not recommendation.evidence_sufficient
