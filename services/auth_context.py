from __future__ import annotations

from pydantic import BaseModel

from models.auth_identity import AuthIdentity
from services.mcp_context import AgeixRequestContext


class AuthenticatedRequestContext(BaseModel):
    """Pairing of authenticated identity and explicit Ageix request context."""

    identity: AuthIdentity
    context: AgeixRequestContext
