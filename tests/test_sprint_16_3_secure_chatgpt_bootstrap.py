from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from ageix_mcp.facade_service import MCPFacadeService
from models.auth_identity import AuthIdentity
from services.auth_service import AuthService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixExternalRequestContext, AgeixRequestContext
from services.project_profile_service import ProjectProfileService
from web.app import create_app
from web.dependencies import get_repo_root


def _seed(tmp_path: Path) -> None:
    ProjectProfileService(tmp_path).register_project("Ageix_Test", "Ageix Test", "python", tmp_path)
    path = tmp_path / ".ageix" / "config" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "enabled": True,
        "mode": "dev_token",
        "tokens": [{
            "name": "chatgpt-dev",
            "token_value": "dev-ageix-token",
            "client_id": "chatgpt",
            "agent_id": "lex",
            "participant_id": "greg",
            "allowed_projects": ["Ageix_Test"],
            "allowed_capabilities": ["identity.current", "ageix.health", "governance.status", "audit.recent"],
        }],
    }), encoding="utf-8")


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_repo_root] = lambda: tmp_path
    return TestClient(app)


def _headers(token: str = "dev-ageix-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _context(session_id: str = "sprint-16-3-session", project_id: str = "Ageix_Test") -> dict[str, str]:
    return {"session_id": session_id, "project_id": project_id}


def test_identity_resolution_derives_agent_from_token(tmp_path: Path):
    _seed(tmp_path)
    identity = AuthService(tmp_path).authenticate_bearer_token("dev-ageix-token")
    context = AuthService(tmp_path).build_resolved_context(identity, session_id="s1", project_id="Ageix_Test")

    assert identity.client_id == "chatgpt"
    assert identity.agent_id == "lex"
    assert context.client_id == "chatgpt"
    assert context.agent_id == "lex"
    assert context.session_id == "s1"
    assert context.project_id == "Ageix_Test"


def test_valid_invalid_and_missing_bearer_token(tmp_path: Path):
    _seed(tmp_path)
    client = _client(tmp_path)

    assert client.get("/health", headers=_headers()).status_code == 200
    assert client.get("/health", headers=_headers("bad-token")).status_code == 403
    assert client.get("/health").status_code == 401


def test_identity_current_reports_authenticated_principal(tmp_path: Path):
    _seed(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(),
        "capability_id": "identity.current",
        "arguments": {},
    })

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["result"]["authenticated"] is True
    assert body["result"]["client_id"] == "chatgpt"
    assert body["result"]["agent_id"] == "lex"
    assert body["result"]["project_id"] == "Ageix_Test"
    assert body["result"]["authority_boundary"]["identity_grants_authority"] is False


def test_request_identity_fields_rejected(tmp_path: Path):
    _seed(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": {"session_id": "s1", "project_id": "Ageix_Test", "agent_id": "admin", "client_id": "trusted-internal"},
        "capability_id": "identity.current",
        "arguments": {},
    })

    assert response.status_code == 422


def test_argument_identity_fields_rejected(tmp_path: Path):
    _seed(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(),
        "capability_id": "identity.current",
        "arguments": {"agent_id": "admin"},
    })

    assert response.status_code == 422
    assert "identity_fields_not_allowed" in response.text


def test_authenticated_client_cannot_bypass_governance_or_access_repository(tmp_path: Path):
    _seed(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(),
        "capability_id": "repository.raw_write",
        "arguments": {"path": "bad.py", "content": "nope"},
    })

    body = response.json()
    # Denied by token capability allowlist before governance execution.
    assert body["success"] is False
    assert body["errors"] == ["capability_not_authorized_for_token"]


def test_authenticated_client_cannot_execute_unauthorized_capability(tmp_path: Path):
    _seed(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", headers=_headers(), json={
        "context": _context(),
        "capability_id": "proposal.submit",
        "arguments": {"objective": "should not run"},
    })

    assert response.json()["success"] is False
    assert response.json()["errors"] == ["capability_not_authorized_for_token"]


def test_capability_receives_identity_context_and_audit_redacts_secret(tmp_path: Path):
    _seed(tmp_path)
    client = _client(tmp_path)
    client.post("/capabilities/execute", headers=_headers(), json={
        "context": _context("audit-session"),
        "capability_id": "ageix.health",
        "arguments": {},
    })

    records = CapabilityAuditService(tmp_path).list_records()
    record = records[-1]
    assert record["client_id"] == "chatgpt"
    assert record["agent_id"] == "lex"
    assert record["project_id"] == "Ageix_Test"
    assert "dev-ageix-token" not in json.dumps(records)
    assert "Authorization" not in json.dumps(records)


def test_mcp_identity_alignment(tmp_path: Path):
    _seed(tmp_path)
    identity = AuthIdentity(
        authenticated=True,
        auth_enabled=True,
        authentication_method="dev_token",
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        allowed_projects=["Ageix_Test"],
    )
    web_context = AuthService(tmp_path).build_resolved_context(identity, session_id="same-session", project_id="Ageix_Test")
    mcp_context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="same-session",
        project_id="Ageix_Test",
        provider="openai",
        display_name="Lex",
        authentication_method="dev_token",
    )

    web_result = MCPFacadeService(tmp_path).execute_tool("ageix.identity.current", web_context, {}).result
    mcp_result = MCPFacadeService(tmp_path).execute_tool("ageix.identity.current", mcp_context, {}).result

    for key in ["client_id", "agent_id", "participant_id", "project_id", "authenticated", "authentication_source"]:
        assert web_result[key] == mcp_result[key]


def test_public_authenticated_access_contract(tmp_path: Path):
    _seed(tmp_path)
    client = _client(tmp_path)
    response = client.get("/capabilities", headers=_headers())

    assert response.status_code == 200
    assert response.json()["metadata"]["auth"]["client_id"] == "chatgpt"
