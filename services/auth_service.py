from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.auth_identity import AuthIdentity
from ageix_mcp.clients.client_registry import MCPClientRegistry
from services.auth_providers.dev_token_provider import DevTokenProvider
from services.auth_providers.jwt_provider import JwtAuthProvider
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
        "jwt": {},
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config_path = self.repo_root / ".ageix" / "config" / "auth.json"
        self.config = self._load_config()

    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def authenticate_bearer_token(self, token: str | None) -> AuthIdentity:
        if not self.is_enabled():
            return AuthIdentity(authenticated=False, auth_enabled=False, authentication_method="disabled", client_id="chatgpt", agent_id="lex")
        if not token:
            raise AuthRequiredError("authentication_required")
        mode = str(self.config.get("mode") or "dev_token")
        if mode == "dev_token":
            identity = DevTokenProvider(list(self.config.get("tokens") or [])).authenticate(token)
            if identity:
                return identity
            raise AuthForbiddenError("invalid_bearer_token")
        if mode in {"jwt", "oauth_jwt", "hybrid"}:
            # Preserve local/dev token support during OAuth rollout and smoke testing.
            dev_identity = DevTokenProvider(list(self.config.get("tokens") or [])).authenticate(token)
            if dev_identity:
                return dev_identity
            identity = JwtAuthProvider(dict(self.config.get("jwt") or self.config.get("oauth") or {})).authenticate(token)
            if identity:
                return identity
            raise AuthForbiddenError("invalid_bearer_token")
        raise AuthForbiddenError(f"unsupported_auth_mode:{mode}")

    def build_resolved_context(
        self,
        identity: AuthIdentity,
        *,
        session_id: str,
        project_id: str,
        client_user_agent: str | None = None,
    ) -> AgeixRequestContext:
        """Create Ageix-owned execution context from credential identity plus request context."""
        participant_id = identity.participant_id if identity.auth_enabled else None
        definition = MCPClientRegistry().get(identity.client_id)
        context = AgeixRequestContext(
            client_id=identity.client_id,
            agent_id=identity.agent_id,
            participant_id=participant_id,
            session_id=session_id,
            project_id=project_id,
            provider=definition.provider if definition else ("openai" if identity.client_id.lower() == "chatgpt" else identity.client_id),
            display_name=definition.display_name if definition else ("Lex" if identity.agent_id == "lex" else identity.agent_id),
            authentication_method=identity.authentication_method,
            client_user_agent=client_user_agent,
        )
        self.validate_context(identity, context)
        return context

    def validate_context(self, identity: AuthIdentity, context: AgeixRequestContext) -> None:
        if not identity.auth_enabled:
            return
        if context.client_id != identity.client_id:
            raise AuthForbiddenError("client_id_not_authorized_for_token")
        if context.agent_id != identity.agent_id:
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

        if "auth_enabled" in data and "enabled" not in data:
            merged["enabled"] = bool(data.get("auth_enabled"))

        if not merged.get("tokens") and data.get("dev_token"):
            merged["tokens"] = [{
                "name": "legacy-dev-token",
                "token_value": data["dev_token"],
                "client_id": str(data.get("client_id") or "chatgpt"),
                "agent_id": str(data.get("agent_id") or "lex"),
                "provider": str(data.get("provider") or "openai"),
                "allowed_projects": list(data.get("allowed_projects") or ["*"]),
                "allowed_capabilities": list(data.get("allowed_capabilities") or ["*"]),
                "authentication_method": "dev_token",
            }]

        if "mode" not in data and data.get("oauth", {}).get("enabled"):
            merged["mode"] = "hybrid"

        if not merged.get("jwt") and data.get("oauth"):
            merged["jwt"] = data["oauth"]

        return merged

class AuthRequiredError(Exception):
    pass


class AuthForbiddenError(Exception):
    pass
