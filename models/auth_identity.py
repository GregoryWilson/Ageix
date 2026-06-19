from __future__ import annotations

from pydantic import BaseModel, Field


class AuthIdentity(BaseModel):
    """Authenticated client identity resolved at the web/MCP boundary.

    Authentication establishes caller identity only. Ageix capability governance
    remains authoritative for what the caller may do.
    """

    authenticated: bool = False
    auth_enabled: bool = False
    authentication_method: str = "disabled"
    token_id: str | None = None
    client_id: str = "dev-disabled"
    participant_id: str | None = None
    allowed_projects: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)

    def project_allowed(self, project_id: str) -> bool:
        return not self.auth_enabled or "*" in self.allowed_projects or project_id in self.allowed_projects

    def agent_allowed(self, agent_id: str) -> bool:
        return not self.auth_enabled or "*" in self.allowed_agents or agent_id in self.allowed_agents
