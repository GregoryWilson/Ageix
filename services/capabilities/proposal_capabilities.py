from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from models.proposal import Proposal, ProposalStatus, ProposalType
from models.evidence_access_proposal import EvidenceAccessProposal
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.proposal_evaluation_service import ProposalEvaluationService
from services.proposal_service import ProposalService


def register_capabilities(repo_root: Path):
    service = ProposalService(repo_root)

    def proposal_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if str(arguments.get("proposal_type") or "") == "evidence_access":
                evidence_proposal = EvidenceAccessProposal(
                    session_id=str(arguments.get("session_id") or ""),
                    agent_id=str(arguments.get("agent_id") or ""),
                    project_id=str(arguments.get("project_id") or ""),
                    objective=str(arguments.get("objective") or ""),
                    reason=str(arguments.get("reason") or ""),
                    requested_evidence=arguments.get("requested_evidence") or [],
                    human_approval=arguments.get("human_approval"),
                )
                decision = EvidenceAccessProposalService(repo_root).evaluate(evidence_proposal)
                return {
                    "success": decision.decision == "approved",
                    "result": decision.model_dump(),
                    "metadata": {
                        "proposal_type": "evidence_access",
                        "requires_proposal": True,
                        **decision.metadata,
                    },
                    "error": None if decision.decision == "approved" else decision.decision,
                }
            proposal = Proposal(
                project_id=str(arguments.get("project_id") or ""),
                session_id=str(arguments.get("session_id") or ""),
                agent_id=str(arguments.get("agent_id") or ""),
                objective=str(arguments.get("objective") or ""),
                proposal_type=ProposalType(str(arguments.get("proposal_type") or "investigation")),
                parent_proposal_id=arguments.get("parent_proposal_id"),
                proposal_version=int(arguments.get("proposal_version") or 1),
                linked_evidence=arguments.get("linked_evidence") or [],
                linked_consultations=arguments.get("linked_consultations") or [],
                required_consultations=arguments.get("required_consultations") or [],
                conditions=arguments.get("conditions") or [],
                metadata=arguments.get("metadata") or {},
            )
            created = service.create_proposal(proposal)
            evaluation = ProposalEvaluationService(repo_root).evaluate(created.proposal_id)
            current = service.get_proposal(created.proposal_id)
            return {
                "success": True,
                "result": {"proposal": current.model_dump(), "evaluation": evaluation.model_dump()},
                "metadata": {"proposal_id": current.proposal_id, "chair_evaluated": True},
            }
        except Exception as exc:
            return {"success": False, "result": {}, "error": str(exc)}

    def proposal_status(arguments: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(arguments.get("proposal_id") or "")
        if not proposal_id:
            return {"success": False, "result": {}, "error": "proposal_id_required"}
        try:
            proposal = service.get_proposal(proposal_id)
            return {"success": True, "result": {"proposal_id": proposal.proposal_id, "status": proposal.status, "proposal_version": proposal.proposal_version}}
        except FileNotFoundError:
            return {"success": False, "result": {}, "error": "proposal_not_found"}

    def proposal_details(arguments: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(arguments.get("proposal_id") or "")
        if not proposal_id:
            return {"success": False, "result": {}, "error": "proposal_id_required"}
        try:
            proposal = service.get_proposal(proposal_id)
            return {"success": True, "result": proposal.model_dump(), "metadata": {"source": "proposal_registry"}}
        except FileNotFoundError:
            return {"success": False, "result": {}, "error": "proposal_not_found"}

    def proposal_list(arguments: dict[str, Any]) -> dict[str, Any]:
        proposals = service.list_proposals(
            project_id=arguments.get("project_id"),
            session_id=arguments.get("session_id"),
            agent_id=arguments.get("agent_id"),
        )
        limit = int(arguments.get("limit") or 50)
        return {
            "success": True,
            "result": {"proposals": [p.model_dump() for p in proposals[:limit]]},
            "metadata": {"source": "proposal_registry"},
        }

    return [
        (CapabilityDefinition(
            capability_id="proposal.submit",
            category="proposal",
            access_level="governed_read",
            handler="proposal.submit",
            description="Submit a governed decision proposal for Chair evaluation without implementation authority.",
            requires_proposal=True,
        ), proposal_submit),
        (CapabilityDefinition(
            capability_id="proposal.status",
            category="proposal",
            access_level="read",
            handler="proposal.status",
            description="Read governed proposal status.",
        ), proposal_status),
        (CapabilityDefinition(
            capability_id="proposal.details",
            category="proposal",
            access_level="read",
            handler="proposal.details",
            description="Read governed proposal details and linked decision material.",
        ), proposal_details),
        (CapabilityDefinition(
            capability_id="proposal.list",
            category="proposal",
            access_level="read",
            handler="proposal.list",
            description="List governed proposals visible to the current session or project.",
        ), proposal_list),
    ]
