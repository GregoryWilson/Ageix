from __future__ import annotations

from pathlib import Path
from typing import Any

from models.auth_identity import AuthIdentity
from ageix_mcp.clients.client_registry import MCPClientRegistry
from services.agent_profile_service import AgentProfileService
from services.mcp_context import AgeixRequestContext


class IdentityResolutionService:
    """Projects authentication/context into an MCP-facing identity description.

    Identity classification is descriptive only. Capability governance remains the
    source of authority for execution decisions.
    """

    PROVIDER_HINTS = {
        "chatgpt": "openai",
        "claude": "anthropic",
        "claude-code": "anthropic",
        "gemini": "google",
        "openwebui": "openwebui",
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.profile_service = AgentProfileService(self.repo_root)
        self.client_registry = MCPClientRegistry()

    def resolve(self, context: AgeixRequestContext, identity: AuthIdentity | None = None) -> dict[str, Any]:
        profile = self.profile_service.get_profile(context.agent_id)
        definition = self.client_registry.get(context.client_id)
        provider = context.provider or (definition.provider if definition else self.PROVIDER_HINTS.get(context.client_id.lower(), context.client_id))
        authenticated = bool(identity.authenticated) if identity is not None else False
        auth_enabled = bool(identity.auth_enabled) if identity is not None else False
        return {
            "client_id": context.client_id,
            "agent_id": context.agent_id,
            "participant_id": context.participant_id,
            "project_id": context.project_id,
            "provider": provider,
            "client_user_agent": context.client_user_agent,
            "agent_type": "external_agent",
            "display_name": context.agent_id,
            "authenticated": authenticated,
            "auth_enabled": auth_enabled,
            "authentication_source": identity.authentication_method if identity is not None else "context_only",
            "token_id": identity.token_id if identity is not None else None,
            "governance_profile": "external_agent",
            "reputation_level": profile.reputation_level,
            "authority_boundary": {
                "identity_grants_authority": False,
                "capability_governance_required": True,
                "chair_authority_preserved": True,
            },
        }
