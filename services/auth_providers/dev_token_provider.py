from __future__ import annotations

import os
from typing import Any

from models.auth_identity import AuthIdentity


class DevTokenProvider:
    """Local development bearer-token provider.

    Token records may provide either token_env, token_value, or both. token_env is
    preferred for real local use so secrets do not need to be committed. Each token
    record owns the authoritative client_id and agent_id.
    """

    def __init__(self, tokens: list[dict[str, Any]] | None = None) -> None:
        self.tokens = tokens or []

    def authenticate(self, token: str) -> AuthIdentity | None:
        for record in self.tokens:
            expected = self._expected_token(record)
            if expected and token == expected:
                agent_id = str(record.get("agent_id") or self._single_allowed_agent(record) or "unknown-agent")
                return AuthIdentity(
                    authenticated=True,
                    auth_enabled=True,
                    authentication_method="dev_token",
                    token_id=str(record.get("name") or record.get("token_env") or "dev-token"),
                    client_id=str(record.get("client_id") or "unknown-client"),
                    agent_id=agent_id,
                    participant_id=record.get("participant_id"),
                    allowed_projects=list(record.get("allowed_projects") or []),
                    allowed_capabilities=list(record.get("allowed_capabilities") or []),
                )
        return None

    def _single_allowed_agent(self, record: dict[str, Any]) -> str | None:
        allowed = list(record.get("allowed_agents") or [])
        return str(allowed[0]) if len(allowed) == 1 else None

    def _expected_token(self, record: dict[str, Any]) -> str | None:
        token_env = record.get("token_env")
        if token_env:
            value = os.environ.get(str(token_env))
            if value:
                return value
        token_value = record.get("token_value")
        return str(token_value) if token_value else None
