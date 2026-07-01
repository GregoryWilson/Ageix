from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.proposal_approval_service import ProposalApprovalService


def register_capabilities(repo_root: Path):
    service = ProposalApprovalService(repo_root)

    def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service.execute(arguments)
        if result.get("success"):
            return {"success": True, "result": result, "metadata": {"source": "proposal_approval_capability"}}
        return {"success": False, "result": result, "error": result.get("error"), "metadata": {"source": "proposal_approval_capability"}}

    return [
        (CapabilityDefinition(
            capability_id="proposal.approval.execute",
            category="proposal",
            access_level="governed_write",
            handler="proposal.approval.execute",
            description="Chair-governed proposal approval actions within the Proposal System lifecycle boundary.",
            requires_proposal=False,
            requires_consultation=False,
            exposed_to_external_agents=True,
        ), handle),
    ]
