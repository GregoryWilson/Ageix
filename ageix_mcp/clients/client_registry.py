from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from models.public_exposure import OutboundNetworkPolicy


@dataclass(frozen=True)
class MCPClientDefinition:
    client_id: str
    display_name: str
    provider: str
    enabled: bool
    primary: bool = False
    placeholder: bool = False
    outbound_network: OutboundNetworkPolicy = field(default_factory=OutboundNetworkPolicy)

    def to_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "enabled": self.enabled,
            "primary": self.primary,
            "placeholder": self.placeholder,
            "outbound_network": self.outbound_network.model_dump(),
        }


DEFAULT_CLIENTS: tuple[MCPClientDefinition, ...] = (
    MCPClientDefinition(
        client_id="chatGPT",
        display_name="Lex",
        provider="chatGPT",
        enabled=True,
        primary=True,
        placeholder=False,
    ),
    MCPClientDefinition("claude", "Claude", "anthropic", enabled=False, placeholder=True),
    MCPClientDefinition("gemini", "Gemini", "google", enabled=False, placeholder=True),
    MCPClientDefinition("openwebui", "OpenWebUI", "openwebui", enabled=False, placeholder=True),
    MCPClientDefinition("custom", "Custom MCP Client", "custom", enabled=False, placeholder=True),
)


class MCPClientRegistry:
    """Lightweight registry for MCP client profile metadata.

    Client identity is descriptive only. It never grants execution authority.
    """

    def __init__(self, clients: Iterable[MCPClientDefinition] | None = None) -> None:
        self._clients: dict[str, MCPClientDefinition] = {}
        for client in clients or DEFAULT_CLIENTS:
            self.register(client)

    def register(self, definition: MCPClientDefinition) -> MCPClientDefinition:
        if not definition.client_id:
            raise ValueError("client_id_required")
        if definition.client_id in self._clients:
            raise ValueError(f"duplicate_mcp_client:{definition.client_id}")
        if definition.primary and any(client.primary for client in self._clients.values()):
            raise ValueError("only_one_primary_mcp_client_allowed")
        self._clients[definition.client_id] = definition
        return definition

    def get(self, client_id: str) -> MCPClientDefinition | None:
        return self._clients.get(client_id)

    def require(self, client_id: str) -> MCPClientDefinition:
        client = self.get(client_id)
        if client is None:
            raise KeyError(client_id)
        return client

    def primary(self) -> MCPClientDefinition:
        for client in self._clients.values():
            if client.primary:
                return client
        raise LookupError("primary_mcp_client_not_configured")

    def list_clients(self, *, include_placeholders: bool = True, include_disabled: bool = True) -> list[dict[str, object]]:
        clients = []
        for client in self._clients.values():
            if not include_disabled and not client.enabled:
                continue
            if not include_placeholders and client.placeholder:
                continue
            clients.append(client.to_dict())
        return sorted(clients, key=lambda item: str(item["client_id"]))
