from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_definition import CapabilityDefinition
from services.agent_profile_service import AgentProfileService
from services.architecture_work_context_service import ArchitectureWorkContextService


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str


class AgentAuthorizationService:
    """Authorizes external agents without letting reputation bypass governance.

    The ADR-0015 role permission table is only enforced for callers that declared
    a known agent_role at session open (see ADR-0014). Callers that never declared
    a role (legacy, non-MCP surfaces) keep the prior reputation-based behavior, so
    this does not retroactively gate surfaces outside the shared-conversation MCP
    boundary this sprint targets.
    """

    DIRECT_BYPASS_CAPABILITIES = {
        "repository.raw_read": "external_agents_cannot_bypass_repository_governance",
        "repository.raw_write": "external_agents_cannot_modify_repository",
        "worker.direct_execute": "external_agents_cannot_directly_execute_workers",
        "promotion.direct_execute": "external_agents_cannot_directly_promote_changes",
    }

    # ADR-0015 capability classes that cut across the access_level dimension.
    CAPABILITY_CLASS_DENY_ROLES = {
        "architecture_propose": {AgentRole.CLAUDE_CODE},
        "work_commission": {AgentRole.CLAUDE_CODE, AgentRole.AGEIX_INTERNAL},
    }
    CAPABILITY_CLASS_ALLOW_ONLY_ROLES = {
        "architecture_approve": {AgentRole.AGEIX_CHAIR},
        "role_override": {AgentRole.AGEIX_CHAIR},
    }
    # system_override sits outside the agent_role model entirely (Greg-only).
    SYSTEM_OVERRIDE_CAPABILITY_CLASS = "system_override"

    PROPOSE_ONLY_ROLES = {AgentRole.CLAUDE_AI, AgentRole.LEX}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.profile_service = AgentProfileService(self.repo_root)
        self.work_context = ArchitectureWorkContextService(self.repo_root)

    def authorize(
        self,
        agent_id: str,
        capability: CapabilityDefinition | None,
        capability_id: str,
        *,
        agent_role: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> AuthorizationDecision:
        if capability_id in self.DIRECT_BYPASS_CAPABILITIES:
            return AuthorizationDecision(False, self.DIRECT_BYPASS_CAPABILITIES[capability_id])
        if capability is None:
            return AuthorizationDecision(False, "unknown_capability")
        if not capability.exposed_to_external_agents and agent_id != "chair":
            return AuthorizationDecision(False, "capability_not_exposed_to_external_agents")
        if not capability.exposed_to_external_agents and agent_id == "chair":
            return AuthorizationDecision(True, "chair_internal_capability_allowed")

        role = AgentRole.parse(agent_role)
        if role is not AgentRole.UNKNOWN:
            decision = self._authorize_role_policy(role, capability, capability_id, arguments or {})
            if decision is not None:
                return decision

        profile = self.profile_service.get_profile(agent_id)
        if capability.access_level == "governed_read":
            return AuthorizationDecision(True, f"governed_read_allowed_for_{profile.reputation_level}")
        if capability.access_level == "governed_write":
            return AuthorizationDecision(True, f"governed_write_allowed_for_{profile.reputation_level}")
        if capability.access_level == "governed_execute":
            return AuthorizationDecision(True, f"governed_execute_allowed_for_{profile.reputation_level}")
        if capability.access_level == "read":
            return AuthorizationDecision(True, f"read_allowed_for_{profile.reputation_level}")
        return AuthorizationDecision(False, "unsupported_external_agent_access_level")

    def _authorize_role_policy(
        self,
        role: AgentRole,
        capability: CapabilityDefinition,
        capability_id: str,
        arguments: dict[str, Any],
    ) -> AuthorizationDecision | None:
        capability_class = self._classify_capability(capability_id)

        if capability_class == self.SYSTEM_OVERRIDE_CAPABILITY_CLASS:
            return AuthorizationDecision(False, "system_override_outside_agent_role_model")
        if capability_class in self.CAPABILITY_CLASS_DENY_ROLES and role in self.CAPABILITY_CLASS_DENY_ROLES[capability_class]:
            return AuthorizationDecision(False, f"{capability_class}_denied_for_role_{role.value}")
        if capability_class in self.CAPABILITY_CLASS_ALLOW_ONLY_ROLES and role not in self.CAPABILITY_CLASS_ALLOW_ONLY_ROLES[capability_class]:
            return AuthorizationDecision(False, f"{capability_class}_restricted_to_chair")

        if capability.access_level != "governed_write":
            return None
        if role is AgentRole.AGEIX_CHAIR:
            return AuthorizationDecision(True, "governed_write_unrestricted_for_chair")
        if role in self.PROPOSE_ONLY_ROLES:
            if capability.requires_proposal:
                return AuthorizationDecision(True, f"governed_write_propose_only_allowed_for_role_{role.value}")
            return AuthorizationDecision(False, f"governed_write_requires_proposal_for_role_{role.value}")
        if role is AgentRole.CLAUDE_CODE:
            return self._check_workctx(arguments, expect_externally_commissioned=True, role=role)
        if role is AgentRole.AGEIX_INTERNAL:
            return self._check_workctx(arguments, expect_externally_commissioned=False, role=role)
        return None

    def _check_workctx(self, arguments: dict[str, Any], *, expect_externally_commissioned: bool, role: AgentRole) -> AuthorizationDecision:
        work_context_id = arguments.get("work_context_id")
        if not work_context_id:
            return AuthorizationDecision(False, f"governed_write_requires_workctx_for_role_{role.value}")
        try:
            package = self.work_context.get_package(str(work_context_id))
        except FileNotFoundError:
            return AuthorizationDecision(False, "workctx_not_found")
        created_by = str(package.get("created_by") or "")
        chair_initiated = created_by in {"chair", AgentRole.AGEIX_CHAIR.value, AgentRole.AGEIX_INTERNAL.value}
        if expect_externally_commissioned and chair_initiated:
            return AuthorizationDecision(False, "workctx_not_externally_commissioned")
        if not expect_externally_commissioned and not chair_initiated:
            return AuthorizationDecision(False, "workctx_not_chair_initiated")
        return AuthorizationDecision(True, f"governed_write_workctx_validated_for_role_{role.value}")

    @staticmethod
    def _classify_capability(capability_id: str) -> str | None:
        if capability_id == "system.override":
            return AgentAuthorizationService.SYSTEM_OVERRIDE_CAPABILITY_CLASS
        if capability_id in {"agent.role_override", "role.override"}:
            return "role_override"
        if capability_id.startswith("architecture.") and capability_id.endswith(".propose"):
            return "architecture_propose"
        if capability_id.startswith("architecture.") and "approve" in capability_id:
            return "architecture_approve"
        if capability_id == "work.commission" or capability_id.startswith("work.commission."):
            return "work_commission"
        return None
