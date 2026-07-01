from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.proposal_approval_service import ProposalApprovalService


def register_capabilities(repo_root: Path):
    service = ProposalApprovalService(repo_root)

    def execute_approval(arguments: dict[str, Any]) -> dict[str, Any]:
        return service.execute(arguments)

    return [
        (CapabilityDefinition(
            capability_id=ProposalApprovalService.CAPABILITY_ID,
            category="proposal",
            access_level="governed_write",
            handler=ProposalApprovalService.CAPABILITY_ID,
            description="Execute target-specific governed proposal approval actions through Proposal System lifecycle state.",
            requires_proposal=False,
            requires_consultation=False,
            exposed_to_external_agents=True,
        ), execute_approval),
    ]
