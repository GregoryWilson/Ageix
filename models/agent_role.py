from __future__ import annotations

from enum import Enum


class AgentRole(str, Enum):
    """Self-declared agent role within a session, per ADR-0014.

    Roles are declared by the calling agent at session open and are NOT
    cryptographically verified — verified identity comes from client_id (JWT).
    UNKNOWN must never be defaulted to; it exists only so callers that omit or
    misdeclare a role can be rejected explicitly rather than silently passed.
    """

    CLAUDE_AI = "claude.ai"
    CLAUDE_CODE = "claude.code"
    LEX = "lex"
    AGEIX_CHAIR = "ageix.chair"
    AGEIX_INTERNAL = "ageix.internal"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: str | None) -> "AgentRole":
        if not value:
            return cls.UNKNOWN
        try:
            return cls(str(value))
        except ValueError:
            return cls.UNKNOWN
