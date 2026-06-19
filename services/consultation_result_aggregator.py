from __future__ import annotations

from collections import Counter

from models.consultation_recommendation import ConsultationDisposition, ConsultationRecommendation
from models.consultation_response import ConsultationResponse
from models.participant_response import ParticipantResponse


class ConsultationResultAggregator:
    """Deterministically aggregates participant responses for the Chair."""

    def aggregate(self, responses: list[ParticipantResponse | ConsultationResponse | dict]) -> ConsultationRecommendation:
        parsed = [self._parse_response(response) for response in responses]
        if not parsed:
            return ConsultationRecommendation()

        dispositions = [response.disposition for response in parsed]
        confidence = sum(response.confidence for response in parsed) / len(parsed)
        consensus = self._detect_consensus(dispositions)
        disagreement = consensus == ConsultationDisposition.DISAGREEMENT
        evidence_sufficient = all(response.evidence_sufficient for response in parsed)

        return ConsultationRecommendation(
            participant_count=len(parsed),
            aggregate_confidence=round(confidence, 4),
            consensus=consensus,
            summary=self._summarize(consensus, len(parsed)),
            recommendations=[response.recommendation for response in parsed if response.recommendation],
            concerns=[concern for response in parsed for concern in response.concerns],
            suggested_improvements=[item for response in parsed for item in response.suggested_improvements],
            participant_ids=[response.participant_id for response in parsed],
            disagreement_detected=disagreement,
            evidence_sufficient=evidence_sufficient,
            metadata={"disposition_counts": dict(Counter(dispositions))},
        )

    def _parse_response(self, response: ParticipantResponse | ConsultationResponse | dict) -> ConsultationResponse:
        if isinstance(response, ConsultationResponse):
            return response
        if isinstance(response, ParticipantResponse):
            return ConsultationResponse(
                participant_id=response.participant_id,
                participant_type="human" if response.participant_id.startswith("human") else "specialist",
                recommendation=response.recommendation,
                confidence=response.confidence,
                disposition=response.disposition,
                evidence_sufficient=response.evidence_sufficient,
                findings=response.findings,
                concerns=response.concerns,
                suggested_improvements=response.suggested_improvements,
                requested_followup_evidence=response.requested_followup_evidence,
                metadata=response.metadata,
            )
        return ConsultationResponse(**response)

    def _detect_consensus(self, dispositions: list[ConsultationDisposition]) -> ConsultationDisposition:
        unique = set(dispositions)
        if ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE in unique:
            return ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE
        if ConsultationDisposition.REJECT in unique:
            return ConsultationDisposition.REJECT if len(unique) == 1 else ConsultationDisposition.DISAGREEMENT
        if ConsultationDisposition.DISAGREEMENT in unique:
            return ConsultationDisposition.DISAGREEMENT
        proceedish = {ConsultationDisposition.PROCEED, ConsultationDisposition.PROCEED_WITH_RECOMMENDATIONS}
        if unique <= proceedish:
            if ConsultationDisposition.PROCEED_WITH_RECOMMENDATIONS in unique:
                return ConsultationDisposition.PROCEED_WITH_RECOMMENDATIONS
            return ConsultationDisposition.PROCEED
        if len(unique) == 1:
            return next(iter(unique))
        return ConsultationDisposition.DISAGREEMENT

    def _summarize(self, consensus: ConsultationDisposition, participant_count: int) -> str:
        if consensus == ConsultationDisposition.PROCEED:
            return f"{participant_count} participant(s) support proceeding."
        if consensus == ConsultationDisposition.PROCEED_WITH_RECOMMENDATIONS:
            return f"{participant_count} participant(s) support proceeding with recommendations."
        if consensus == ConsultationDisposition.BLOCKED_INSUFFICIENT_EVIDENCE:
            return "Consultation is blocked because at least one participant requires additional brokered evidence."
        if consensus == ConsultationDisposition.DISAGREEMENT:
            return "Participants disagree on the consultation disposition."
        if consensus == ConsultationDisposition.REJECT:
            return "Participant responses recommend rejection."
        return "Participants recommend caution before proceeding."
