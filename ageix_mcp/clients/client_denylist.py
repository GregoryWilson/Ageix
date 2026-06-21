from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MCPClientDenylist:
    """Policy-driven MCP client denylist.

    This is intentionally client/provider focused. Network and country controls
    belong at the edge layer when Ageix is publicly exposed.
    """

    blocked_client_ids: frozenset[str] = field(default_factory=lambda: frozenset({"grok"}))
    blocked_providers: frozenset[str] = field(default_factory=lambda: frozenset({"xai"}))
    blocked_aliases: frozenset[str] = field(default_factory=lambda: frozenset({"grok", "xai", "x.ai", "grok-3", "grok3"}))

    def is_blocked(self, *values: object) -> bool:
        normalized = {str(value).strip().lower() for value in values if value is not None and str(value).strip()}
        return bool(
            normalized & self.blocked_client_ids
            or normalized & self.blocked_providers
            or normalized & self.blocked_aliases
        )
