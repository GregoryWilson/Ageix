from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from services.auth_service import AuthService
from services.capability_audit_service import CapabilityAuditService
from services.project_profile_service import ProjectProfileService
from web.app import create_app
from web.dependencies import get_repo_root


ISSUER = "https://keycloak.example.com/realms/ageix"
AUDIENCE = "ageix-mcp"


def _private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwt(private_key, *, scope: str | None = None, client_id: str = "chatgpt") -> str:
    payload = {
        "iss": ISSUER,
        "sub": "chatgpt-user-1",
        "aud": AUDIENCE,
        "azp": client_id,
        "preferred_username": "greg",
        "scope": scope or "openid profile email ageix.project:Ageix_Test ageix.capability:ageix.health ageix.capability:identity.current ageix.capability:capabilities.list",
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test-key"})


def _seed(tmp_path: Path, *, mode: str = "jwt") -> None:
    ProjectProfileService(tmp_path).register_project("Ageix_Test", "Ageix Test", "python", tmp_path)
    path = tmp_path / ".ageix" / "config" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "enabled": True,
        "mode": mode,
        "tokens": [{
            "name": "chatgpt-dev",
            "token_value": "dev-ageix-token",
            "client_id": "chatgpt",
            "agent_id": "lex",
            "participant_id": "greg",
            "allowed_projects": ["Ageix_Test"],
            "allowed_capabilities": ["ageix.health"],
        }],
        "jwt": {
            "issuer": ISSUER,
            "audience": AUDIENCE,
            "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
            "default_agent_id": "lex",
            "default_allowed_projects": [],
            "default_allowed_capabilities": [],
            "claim_map": {"participant_id": "preferred_username"},
        },
    }), encoding="utf-8")


def _client(tmp_path: Path) -> TestClient:
    app = create_app(repo_root=tmp_path)
    app.dependency_overrides[get_repo_root] = lambda: tmp_path
    return TestClient(app)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_oauth_discovery_endpoints_for_chatgpt_paths(tmp_path: Path):
    _seed(tmp_path)
    client = _client(tmp_path)

    for path in ["/.well-known/oauth-protected-resource/mcp", "/mcp/.well-known/oauth-protected-resource"]:
        body = client.get(path).json()
        assert body["resource"].endswith("/mcp")
        assert body["authorization_servers"] == [ISSUER]
        assert "header" in body["bearer_methods_supported"]

    for path in ["/.well-known/oauth-authorization-server/mcp", "/mcp/.well-known/oauth-authorization-server", "/.well-known/openid-configuration", "/mcp/.well-known/openid-configuration"]:
        body = client.get(path).json()
        assert body["issuer"] == ISSUER
        assert body["authorization_endpoint"] == f"{ISSUER}/protocol/openid-connect/auth"
        assert body["token_endpoint"] == f"{ISSUER}/protocol/openid-connect/token"
        assert body["jwks_uri"] == f"{ISSUER}/protocol/openid-connect/certs"
        assert "S256" in body["code_challenge_methods_supported"]


def test_jwt_validation_maps_claims_and_scopes_to_identity(tmp_path: Path, monkeypatch):
    private_key = _private_key()
    public_key = private_key.public_key()
    monkeypatch.setattr("services.auth_providers.jwt_provider.PyJWKClient.get_signing_key_from_jwt", lambda self, token: SimpleNamespace(key=public_key))
    _seed(tmp_path)

    token = _jwt(private_key)
    identity = AuthService(tmp_path).authenticate_bearer_token(token)

    assert identity.authentication_method == "jwt"
    assert identity.client_id == "chatgpt"
    assert identity.agent_id == "lex"
    assert identity.participant_id == "greg"
    assert identity.project_allowed("Ageix_Test")
    assert identity.capability_allowed("ageix.health")
    assert not identity.capability_allowed("repository.raw_read")


def test_jwt_authenticated_request_preserves_capability_authorization_and_audit(tmp_path: Path, monkeypatch):
    private_key = _private_key()
    public_key = private_key.public_key()
    monkeypatch.setattr("services.auth_providers.jwt_provider.PyJWKClient.get_signing_key_from_jwt", lambda self, token: SimpleNamespace(key=public_key))
    _seed(tmp_path)
    token = _jwt(private_key)
    client = _client(tmp_path)

    ok = client.post("/capabilities/execute", headers=_headers(token), json={
        "context": {"session_id": "jwt-audit", "project_id": "Ageix_Test"},
        "capability_id": "ageix.health",
        "arguments": {},
    })
    denied = client.post("/capabilities/execute", headers=_headers(token), json={
        "context": {"session_id": "jwt-audit", "project_id": "Ageix_Test"},
        "capability_id": "repository.raw_read",
        "arguments": {"path": "services/auth_service.py"},
    })

    assert ok.status_code == 200
    assert ok.json()["success"] is True
    assert ok.json()["metadata"]["authenticated_client_id"] == "chatgpt"
    assert denied.json()["success"] is False
    assert denied.json()["errors"] == ["capability_not_authorized_for_token"]

    records = CapabilityAuditService(tmp_path).list_records()
    assert any(record["session_id"] == "jwt-audit" and record["client_id"] == "chatgpt" and record["agent_id"] == "lex" for record in records)
    assert token not in json.dumps(records)


def test_hybrid_mode_keeps_dev_token_support(tmp_path: Path):
    _seed(tmp_path, mode="hybrid")
    identity = AuthService(tmp_path).authenticate_bearer_token("dev-ageix-token")

    assert identity.authentication_method == "dev_token"
    assert identity.client_id == "chatgpt"
    assert identity.capability_allowed("ageix.health")
