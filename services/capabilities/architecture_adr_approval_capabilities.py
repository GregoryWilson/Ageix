from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.architecture_adr_approval_service import ArchitectureAdrApprovalService


def register_capabilities(repo_root: Path):
    service = ArchitectureAdrApprovalService(repo_root)

    def execute_approval(arguments: dict[str, Any]) -> dict[str, Any]:
        return service.execute(arguments)

    return [
        (CapabilityDefinition(
            capability_id=ArchitectureAdrApprovalService.CAPABILITY_ID,
            category="architecture",
            access_level="governed_execute",
            handler=ArchitectureAdrApprovalService.CAPABILITY_ID,
            description="Execute target-specific governed Architecture ADR approval actions through ADR lifecycle governance.",
            requires_proposal=False,
            requires_consultation=False,
            exposed_to_external_agents=True,
        ), execute_approval),
    ]
