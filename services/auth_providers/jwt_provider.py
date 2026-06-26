from __future__ import annotations

import time
import urllib.request
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from models.auth_identity import AuthIdentity


class JwtAuthProvider:
    """OIDC/JWT bearer-token provider backed by an issuer JWKS.

    Authentication only resolves transport identity. Capability authorization is
    still enforced by Ageix allowlists and Chair governance after authentication.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config or {}
        self.issuer = str(self.config.get("issuer") or "").rstrip("/")
        self.jwks_uri = str(self.config.get("jwks_uri") or (f"{self.issuer}/protocol/openid-connect/certs" if self.issuer else ""))
        self.audience = self.config.get("audience") or self.config.get("client_id")
        self.algorithms = list(self.config.get("algorithms") or ["RS256"])
        self.leeway = int(self.config.get("leeway_seconds") or 30)

    def authenticate(self, token: str) -> AuthIdentity | None:
        if not self.issuer or not self.jwks_uri:
            return None
        try:
            signing_key = PyJWKClient(self.jwks_uri).get_signing_key_from_jwt(token).key
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway,
                options={"verify_aud": bool(self.audience)},
            )
        except Exception:
            return None
        return self._identity_from_claims(payload)

    def _identity_from_claims(self, claims: dict[str, Any]) -> AuthIdentity:
        claim_map = dict(self.config.get("claim_map") or {})
        scope_prefix = str(self.config.get("capability_scope_prefix") or "ageix.capability:")
        project_scope_prefix = str(self.config.get("project_scope_prefix") or "ageix.project:")

        scopes = _scope_values(claims)
        capability_scopes = [s.removeprefix(scope_prefix) for s in scopes if s.startswith(scope_prefix)]
        project_scopes = [s.removeprefix(project_scope_prefix) for s in scopes if s.startswith(project_scope_prefix)]

        allowed_capabilities = list(self.config.get("default_allowed_capabilities") or []) + capability_scopes
        allowed_projects = list(self.config.get("default_allowed_projects") or []) + project_scopes

        client_id = _first_claim(claims, claim_map.get("client_id"), default=None) or claims.get("azp") or claims.get("client_id") or "chatgpt"
        agent_id = _first_claim(claims, claim_map.get("agent_id"), default=None) or self.config.get("default_agent_id") or "lex"
        participant_id = _first_claim(claims, claim_map.get("participant_id"), default=None) or claims.get("preferred_username") or claims.get("sub")

        return AuthIdentity(
            authenticated=True,
            auth_enabled=True,
            authentication_method="jwt",
            token_id=str(claims.get("jti") or claims.get("sid") or claims.get("sub") or "jwt"),
            client_id=str(client_id),
            agent_id=str(agent_id),
            participant_id=str(participant_id) if participant_id else None,
            allowed_projects=_dedupe(allowed_projects),
            allowed_capabilities=_dedupe(allowed_capabilities),
            scopes=scopes,
            issuer=str(claims.get("iss")) if claims.get("iss") else None,
            subject=str(claims.get("sub")) if claims.get("sub") else None,
        )


def _scope_values(claims: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw_scope = claims.get("scope")
    if isinstance(raw_scope, str):
        values.extend(raw_scope.split())
    realm_access = claims.get("realm_access") or {}
    if isinstance(realm_access, dict):
        roles = realm_access.get("roles") or []
        if isinstance(roles, list):
            values.extend(str(role) for role in roles)
    resource_access = claims.get("resource_access") or {}
    if isinstance(resource_access, dict):
        for access in resource_access.values():
            if isinstance(access, dict):
                roles = access.get("roles") or []
                if isinstance(roles, list):
                    values.extend(str(role) for role in roles)
    return _dedupe(values)


def _first_claim(claims: dict[str, Any], names: Any, *, default: Any = None) -> Any:
    if not names:
        return default
    if isinstance(names, str):
        names = [names]
    for name in names:
        if name in claims and claims[name] not in {None, ""}:
            return claims[name]
    return default


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result
