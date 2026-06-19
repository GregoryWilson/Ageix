from __future__ import annotations

from pathlib import Path

from models.proposal import Proposal, ProposalEvaluationResult, ProposalStatus, ProposalType
from services.proposal_service import ProposalService


DEFAULT_CONSULTATIONS = {
    ProposalType.ARCHITECTURE: ["architecture_review"],
    ProposalType.IMPLEMENTATION: ["implementation_review"],
    ProposalType.GOVERNANCE: ["governance_review"],
    ProposalType.RISK: ["risk_review"],
}


class ProposalEvaluationService:
    """Chair-side proposal evaluator. It returns dispositions; it does not execute work."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.service = ProposalService(repo_root)

    def evaluate(self, proposal_id: str) -> ProposalEvaluationResult:
        proposal = self.service.get_proposal(proposal_id)
        return self.evaluate_proposal(proposal)

    def evaluate_proposal(self, proposal: Proposal) -> ProposalEvaluationResult:
        reasons: list[str] = []
        missing_evidence: list[str] = []
        required_consultations = list(proposal.required_consultations)
        for item in DEFAULT_CONSULTATIONS.get(proposal.proposal_type, []):
            if item not in required_consultations:
                required_consultations.append(item)

        if not proposal.linked_evidence and proposal.proposal_type in {ProposalType.IMPLEMENTATION, ProposalType.VALIDATION}:
            missing_evidence.append("proposal_requires_supporting_evidence")
            reasons.append("evidence_sufficiency_not_met")

        accepted_types = set(proposal.accepted_consultations or proposal.linked_consultations)
        missing_consultations = [item for item in required_consultations if item not in accepted_types]
        if missing_consultations:
            reasons.append("proposal_requires_consultation")
            disposition = "consultation_required"
            status = ProposalStatus.AWAITING_CONSULTATION
        elif missing_evidence:
            disposition = "needs_more_evidence"
            status = ProposalStatus.AWAITING_EVIDENCE
        elif "deny" in proposal.objective.lower() or proposal.metadata.get("deny") is True:
            disposition = "denied"
            status = ProposalStatus.DENIED
            reasons.append("proposal_failed_chair_policy_review")
        elif proposal.conditions:
            disposition = "approved_with_conditions"
            status = ProposalStatus.APPROVED_WITH_CONDITIONS
        else:
            disposition = "approved"
            status = ProposalStatus.APPROVED

        self.service.update_status(
            proposal.proposal_id,
            status,
            required_consultations=required_consultations,
        )
        return ProposalEvaluationResult(
            proposal_id=proposal.proposal_id,
            disposition=disposition,
            evidence_sufficient=not missing_evidence,
            consultation_required=bool(missing_consultations),
            approval_required=disposition in {"approved", "approved_with_conditions"},
            missing_evidence=missing_evidence,
            required_consultations=missing_consultations,
            conditions=proposal.conditions,
            reasons=reasons,
            metadata={"chair_authoritative": True, "repository_modified": False, "worker_executed": False},
        )
