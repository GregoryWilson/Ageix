from __future__ import annotations

from pydantic import BaseModel, Field


class AuthIdentity(BaseModel):
    """Authenticated client principal resolved at the web/MCP boundary.

    Authentication establishes identity only. Ageix capability governance remains
    authoritative for what the caller may do. The agent_id is credential-derived
    and must not be accepted from external request payloads.
    """

    authenticated: bool = False
    auth_enabled: bool = False
    authentication_method: str = "disabled"
    token_id: str | None = None
    client_id: str = "dev-disabled"
    agent_id: str = "dev-disabled"
    participant_id: str | None = None
    allowed_projects: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)

    def project_allowed(self, project_id: str) -> bool:
        return not self.auth_enabled or "*" in self.allowed_projects or project_id in self.allowed_projects

    def capability_allowed(self, capability_id: str) -> bool:
        if not self.auth_enabled or not self.allowed_capabilities or "*" in self.allowed_capabilities:
            return True
        return any(
            capability_id == allowed or (allowed.endswith(".*") and capability_id.startswith(allowed[:-1]))
            for allowed in self.allowed_capabilities
        )

    @property
    def allowed_agents(self) -> list[str]:
        # Backward-compatible read-only view for older internal tests/helpers.
        return [self.agent_id] if self.agent_id else []

    def agent_allowed(self, agent_id: str) -> bool:
        return not self.auth_enabled or agent_id == self.agent_id
