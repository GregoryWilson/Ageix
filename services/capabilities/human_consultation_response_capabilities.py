from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.human_consultation_service import HumanConsultationService


def register_capabilities(repo_root: Path):
    service = HumanConsultationService(repo_root)

    def execute_response(arguments: dict[str, Any]) -> dict[str, Any]:
        return service.respond(arguments)

    definition = CapabilityDefinition(
        capability_id=HumanConsultationService.CAPABILITY_ID,
        category="human_consultation",
        access_level="governed_write",
        handler=HumanConsultationService.CAPABILITY_ID,
        description="Submit a constrained response to an Ageix-owned human consultation request.",
        requires_proposal=False,
        requires_consultation=False,
        exposed_to_external_agents=True,
    )
    return [(definition, execute_response)]
