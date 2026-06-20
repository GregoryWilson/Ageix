from __future__ import annotations

from dataclasses import dataclass, field

from mcp.clients.client_registry import MCPClientDefinition, MCPClientRegistry


@dataclass(frozen=True)
class ChatGPTClientProfile:
    """Descriptive Lex/ChatGPT MCP client behavior profile.

    This profile describes expected discovery, session, workflow, and governance
    behavior. It does not provide execution authority.
    """

    client_id: str = "chatgpt"
    display_name: str = "Lex"
    provider: str = "openai"
    agent_id: str = "lex"
    discovery_behavior: dict[str, object] = field(default_factory=lambda: {
        "uses_mcp_discovery": True,
        "requires_input_schema": True,
        "requires_workflow_hints": True,
        "hardcoded_workflow_paths_allowed": False,
    })
    session_initialization_behavior: dict[str, object] = field(default_factory=lambda: {
        "initial_tool": "ageix.workflow.current",
        "persists_client_context": True,
        "session_context_grants_authority": False,
    })
    workflow_navigation_behavior: dict[str, object] = field(default_factory=lambda: {
        "uses_recommended_next_tools": True,
        "tracks_active_proposal": True,
        "tracks_active_consultations": True,
    })
    governance_expectations: dict[str, object] = field(default_factory=lambda: {
        "identity_grants_authority": False,
        "capability_governance_required": True,
        "chair_authority_preserved": True,
        "unauthorized_execution_denied": True,
    })

    @classmethod
    def resolve(cls, registry: MCPClientRegistry | None = None) -> "ChatGPTClientProfile":
        client = (registry or MCPClientRegistry()).require("chatgpt")
        if not client.enabled or client.placeholder:
            raise ValueError("chatgpt_client_profile_not_enabled")
        return cls.from_definition(client)

    @classmethod
    def from_definition(cls, client: MCPClientDefinition) -> "ChatGPTClientProfile":
        return cls(client_id=client.client_id, display_name=client.display_name, provider=client.provider)

    def client_context(self, *, session_id: str, project_id: str, participant_id: str | None = None) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "agent_id": self.agent_id,
            "session_id": session_id,
            "project_id": project_id,
            "participant_id": participant_id,
            "authority_granted": False,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "agent_id": self.agent_id,
            "discovery_behavior": self.discovery_behavior,
            "session_initialization_behavior": self.session_initialization_behavior,
            "workflow_navigation_behavior": self.workflow_navigation_behavior,
            "governance_expectations": self.governance_expectations,
            "authority_granted": False,
        }
