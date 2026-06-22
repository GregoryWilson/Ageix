from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from models.evidence_access_proposal import EvidenceAccessProposal
from services.evidence_access_proposal_service import EvidenceAccessProposalService


def register_capabilities(repo_root: Path):
    def evidence_request(arguments: dict[str, Any]) -> dict[str, Any]:
        proposal = EvidenceAccessProposal(
            session_id=str(arguments.get("session_id") or ""),
            agent_id=str(arguments.get("agent_id") or ""),
            project_id=str(arguments.get("project_id") or ""),
            objective=str(arguments.get("objective") or ""),
            reason=str(arguments.get("reason") or ""),
            request_mode=str(arguments.get("request_mode") or "explicit"),
            requested_evidence=arguments.get("requested_evidence") or [],
            target=arguments.get("target"),
            desired_outcome=arguments.get("desired_outcome"),
            intent_type=str(arguments.get("intent_type") or "unknown"),
            human_approval=arguments.get("human_approval"),
        )
        decision = EvidenceAccessProposalService(repo_root).evaluate(proposal)
        return {
            "success": decision.decision == "approved",
            "result": decision.model_dump(),
            "metadata": {
                "proposal_type": "evidence_access",
                "requires_proposal": True,
                "request_mode": proposal.request_mode,
                **decision.metadata,
            },
            "error": None if decision.decision == "approved" else decision.decision,
        }

    return [
        (CapabilityDefinition(
            capability_id="evidence.request",
            category="evidence",
            access_level="governed_read",
            handler="evidence.request",
            description="Request scoped repository evidence through a Chair-governed evidence access proposal.",
            requires_proposal=True,
        ), evidence_request),
        (CapabilityDefinition(
            capability_id="evidence.proposal.submit",
            category="evidence",
            access_level="governed_read",
            handler="evidence.proposal.submit",
            description="Submit a governed evidence-access proposal.",
            requires_proposal=True,
        ), evidence_request),
    ]
