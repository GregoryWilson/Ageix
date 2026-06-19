from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.auth_identity import AuthIdentity
from services.auth_providers.dev_token_provider import DevTokenProvider
from services.mcp_context import AgeixRequestContext


class AuthService:
    """Authentication boundary service for web/MCP callers.

    This service intentionally does not grant Ageix capability authority. It only
    resolves caller identity and validates that the request context is consistent
    with that identity before governed services execute.
    """

    DEFAULT_CONFIG: dict[str, Any] = {
        "enabled": False,
        "mode": "dev_token",
        "tokens": [],
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config_path = self.repo_root / ".ageix" / "config" / "auth.json"
        self.config = self._load_config()

    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def authenticate_bearer_token(self, token: str | None) -> AuthIdentity:
        if not self.is_enabled():
            return AuthIdentity(authenticated=False, auth_enabled=False, authentication_method="disabled")
        if not token:
            raise AuthRequiredError("authentication_required")
        mode = str(self.config.get("mode") or "dev_token")
        if mode == "dev_token":
            identity = DevTokenProvider(list(self.config.get("tokens") or [])).authenticate(token)
            if identity:
                return identity
            raise AuthForbiddenError("invalid_bearer_token")
        raise AuthForbiddenError(f"unsupported_auth_mode:{mode}")

    def validate_context(self, identity: AuthIdentity, context: AgeixRequestContext) -> None:
        if not identity.auth_enabled:
            return
        if context.client_id != identity.client_id:
            raise AuthForbiddenError("client_id_not_authorized_for_token")
        if not identity.agent_allowed(context.agent_id):
            raise AuthForbiddenError("agent_id_not_authorized_for_token")
        if not identity.project_allowed(context.project_id):
            raise AuthForbiddenError("project_id_not_authorized_for_token")
        if identity.participant_id and context.participant_id and context.participant_id != identity.participant_id:
            raise AuthForbiddenError("participant_id_not_authorized_for_token")

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return dict(self.DEFAULT_CONFIG)
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        merged = dict(self.DEFAULT_CONFIG)
        merged.update(data)
        return merged


class AuthRequiredError(Exception):
    pass


class AuthForbiddenError(Exception):
    pass
