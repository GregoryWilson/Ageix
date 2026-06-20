from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.capability_definition import CapabilityDefinition
from services.agent_profile_service import AgentProfileService


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str


class AgentAuthorizationService:
    """Authorizes external agents without letting reputation bypass governance."""

    DIRECT_BYPASS_CAPABILITIES = {
        "repository.raw_read": "external_agents_cannot_bypass_repository_governance",
        "repository.raw_write": "external_agents_cannot_modify_repository",
        "worker.direct_execute": "external_agents_cannot_directly_execute_workers",
        "promotion.direct_execute": "external_agents_cannot_directly_promote_changes",
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.profile_service = AgentProfileService(repo_root)

    def authorize(self, agent_id: str, capability: CapabilityDefinition | None, capability_id: str) -> AuthorizationDecision:
        if capability_id in self.DIRECT_BYPASS_CAPABILITIES:
            return AuthorizationDecision(False, self.DIRECT_BYPASS_CAPABILITIES[capability_id])
        if capability is None:
            return AuthorizationDecision(False, "unknown_capability")
        if not capability.exposed_to_external_agents:
            return AuthorizationDecision(False, "capability_not_exposed_to_external_agents")
        profile = self.profile_service.get_profile(agent_id)
        if capability.access_level == "governed_read":
            return AuthorizationDecision(True, f"governed_read_allowed_for_{profile.reputation_level}")
        if capability.access_level == "read":
            return AuthorizationDecision(True, f"read_allowed_for_{profile.reputation_level}")
        return AuthorizationDecision(False, "unsupported_external_agent_access_level")
