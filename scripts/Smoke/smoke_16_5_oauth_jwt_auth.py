from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from services.auth_service import AuthService
from services.project_profile_service import ProjectProfileService
from web.app import create_app
from web.dependencies import get_repo_root


ISSUER = "https://keycloak.example.com/realms/ageix"
AUDIENCE = "ageix-mcp"


def main() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    import services.auth_providers.jwt_provider as jwt_provider
    jwt_provider.PyJWKClient.get_signing_key_from_jwt = lambda self, token: SimpleNamespace(key=public_key)  # type: ignore[method-assign]

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        ProjectProfileService(repo_root).register_project("Ageix_Test", "Ageix Test", "python", repo_root)
        config_path = repo_root / ".ageix" / "config" / "auth.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            "enabled": True,
            "mode": "hybrid",
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
            },
        }), encoding="utf-8")

        app = create_app(repo_root=repo_root)
        app.dependency_overrides[get_repo_root] = lambda: repo_root
        client = TestClient(app)

        print("== Smoke 16.5: OAuth discovery and JWT auth ==")
        for path in [
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-authorization-server/mcp",
            "/.well-known/openid-configuration",
            "/mcp/.well-known/oauth-protected-resource",
            "/mcp/.well-known/oauth-authorization-server",
            "/mcp/.well-known/openid-configuration",
        ]:
            response = client.get(path)
            print(path, response.status_code)
            assert response.status_code == 200

        token = jwt.encode({
            "iss": ISSUER,
            "sub": "chatgpt-user-1",
            "aud": AUDIENCE,
            "azp": "chatgpt",
            "preferred_username": "greg",
            "scope": "openid profile email ageix.project:Ageix_Test ageix.capability:ageix.health",
        }, private_key, algorithm="RS256", headers={"kid": "test-key"})

        identity = AuthService(repo_root).authenticate_bearer_token(token)
        print("jwt identity:", identity.model_dump())
        assert identity.authentication_method == "jwt"
        assert identity.client_id == "chatgpt"
        assert identity.agent_id == "lex"
        assert identity.project_allowed("Ageix_Test")
        assert identity.capability_allowed("ageix.health")

        result = client.post("/capabilities/execute", headers={"Authorization": f"Bearer {token}"}, json={
            "context": {"session_id": "smoke-16-5", "project_id": "Ageix_Test"},
            "capability_id": "ageix.health",
            "arguments": {},
        }).json()
        print("ageix.health:", result)
        assert result["success"] is True

        dev_identity = AuthService(repo_root).authenticate_bearer_token("dev-ageix-token")
        assert dev_identity.authentication_method == "dev_token"

    print("Smoke 16.5 PASS")


if __name__ == "__main__":
    main()
