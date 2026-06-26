from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.project_profile_service import ProjectProfileService
from web.app import create_app
from web.dependencies import get_repo_root


def _seed_project(tmp_path: Path, project_id: str = "Ageix_Test") -> None:
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def _write_auth_config(tmp_path: Path, *, enabled: bool = True) -> None:
    path = tmp_path / ".ageix" / "config" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "enabled": enabled,
        "mode": "dev_token",
        "tokens": [
            {
                "name": "chatgpt-dev",
                "token_value": "dev-ageix-token",
                "client_id": "chatgpt",
                "participant_id": "greg",
                "allowed_projects": ["Ageix_Test"],
                "allowed_agents": ["lex"],
            }
        ],
    }), encoding="utf-8")


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_repo_root] = lambda: tmp_path
    return TestClient(app)


def _headers(token: str = "dev-ageix-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _context(**overrides: str) -> dict[str, str]:
    context = {
        "session_id": "sprint-14-1-session",
        "project_id": "Ageix_Test",
    }
    context.update(overrides)
    return context


def test_auth_disabled_preserves_dev_mode_access(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=False)

    response = _client(tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["metadata"]["auth_enabled"] is False


def test_auth_enabled_requires_bearer_token(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)

    response = _client(tmp_path).get("/health")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_auth_enabled_rejects_invalid_bearer_token(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)

    response = _client(tmp_path).get("/health", headers=_headers("bad-token"))

    assert response.status_code == 403
    assert response.json()["detail"] == "invalid_bearer_token"


def test_auth_enabled_allows_valid_bearer_token(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)

    response = _client(tmp_path).get("/health", headers=_headers())

    assert response.status_code == 200
    assert response.json()["metadata"]["auth_enabled"] is True
    assert response.json()["metadata"]["client_id"] == "chatgpt"


def test_authenticated_context_rejects_client_identity_field(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)
    _seed_project(tmp_path)

    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(client_id="claude"),
        "capability_id": "ageix.health",
        "arguments": {},
    })

    assert response.status_code == 422


def test_authenticated_context_rejects_agent_identity_field(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)
    _seed_project(tmp_path)

    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(agent_id="gemini"),
        "capability_id": "ageix.health",
        "arguments": {},
    })

    assert response.status_code == 422


def test_authenticated_context_must_match_project(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)
    _seed_project(tmp_path)

    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(project_id="Other_Project"),
        "capability_id": "ageix.health",
        "arguments": {},
    })

    assert response.status_code == 403
    assert response.json()["detail"] == "project_id_not_authorized_for_token"


def test_authenticated_governance_denial_remains_standard_envelope(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)
    _seed_project(tmp_path)

    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(),
        "capability_id": "repository.raw_write",
        "arguments": {"path": "bad.py", "content": "nope"},
    })

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["errors"] == ["external_agents_cannot_modify_repository"]
    assert response.json()["governance"]["chair_authority_preserved"] is True


def test_auth_aware_audit_records_client_and_project(tmp_path: Path):
    _write_auth_config(tmp_path, enabled=True)
    _seed_project(tmp_path)
    client = _client(tmp_path)

    client.post("/capabilities/execute", headers=_headers(), json={
        "context": _context(),
        "capability_id": "ageix.health",
        "arguments": {},
    })
    response = client.get("/audit/recent", headers=_headers(), params=_context())

    assert response.status_code == 200
    record = response.json()["result"]["records"][-1]
    assert record["client_id"] == "chatgpt"
    assert record["project_id"] == "Ageix_Test"
    assert record["participant_id"] == "greg"
