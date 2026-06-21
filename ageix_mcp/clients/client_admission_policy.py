from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ageix_mcp.clients.client_denylist import MCPClientDenylist
from ageix_mcp.clients.client_registry import MCPClientRegistry


@dataclass(frozen=True)
class ClientAdmissionDecision:
    allowed: bool
    reason: str
    security_violation: bool = False
    resolved_client_id: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "security_violation": self.security_violation,
            "resolved_client_id": self.resolved_client_id,
            **(self.metadata or {}),
        }


class MCPClientAdmissionPolicy:
    """Evaluates whether a claimed MCP client may reach governed capabilities.

    Admission is not authorization. Passing admission only means the request is
    allowed to continue to normal capability authorization and Chair governance.
    """

    def __init__(self, registry: MCPClientRegistry | None = None, denylist: MCPClientDenylist | None = None) -> None:
        self.registry = registry or MCPClientRegistry()
        self.denylist = denylist or MCPClientDenylist()

    def evaluate(
        self,
        *,
        client_id: str,
        provider: str | None = None,
        display_name: str | None = None,
        agent_id: str | None = None,
        claimed_primary: bool | None = None,
    ) -> ClientAdmissionDecision:
        if self.denylist.is_blocked(client_id, provider, display_name, agent_id):
            return ClientAdmissionDecision(False, "mcp_client_denylisted", True, str(client_id or "unknown"), {"blocked": True})

        definition = self.registry.get(client_id)
        if definition is None:
            return ClientAdmissionDecision(False, "mcp_client_unknown", True, client_id)
        if not definition.enabled:
            return ClientAdmissionDecision(False, "mcp_client_disabled", False, definition.client_id, {"placeholder": definition.placeholder})
        if definition.placeholder:
            return ClientAdmissionDecision(False, "mcp_client_placeholder_denied", False, definition.client_id, {"placeholder": True})

        if provider is not None and provider != definition.provider:
            return ClientAdmissionDecision(
                False,
                "mcp_client_provider_mismatch",
                True,
                definition.client_id,
                {"expected_provider": definition.provider, "claimed_provider": provider},
            )
        if display_name is not None and display_name != definition.display_name:
            return ClientAdmissionDecision(
                False,
                "mcp_client_display_name_mismatch",
                True,
                definition.client_id,
                {"expected_display_name": definition.display_name, "claimed_display_name": display_name},
            )
        if claimed_primary is True and not definition.primary:
            return ClientAdmissionDecision(False, "mcp_client_primary_claim_denied", True, definition.client_id)
        if definition.client_id == "chatgpt" and agent_id is not None and agent_id != "lex":
            return ClientAdmissionDecision(
                False,
                "mcp_client_agent_mismatch",
                True,
                definition.client_id,
                {"expected_agent_id": "lex", "claimed_agent_id": agent_id},
            )

        return ClientAdmissionDecision(True, "mcp_client_admitted", False, definition.client_id, definition.to_dict())
