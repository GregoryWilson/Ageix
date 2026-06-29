from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from services.capability_audit_service import CapabilityAuditService
from services.project_profile_service import ProjectProfileService
from web.dependencies import get_repo_root


REGISTERED_TOOLS: dict[str, Any] = {}


class FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name
        self.registered = REGISTERED_TOOLS

    def tool(self, name: str):
        def decorate(fn):
            self.registered[name] = fn
            return fn
        return decorate

    def http_app(self, path: str = "/"):
        async def root(request: Request):
            return JSONResponse({"transport": "fastmcp", "path": path, "tools": sorted(self.registered)})

        async def call(request: Request):
            payload = await request.json()
            fn = self.registered[payload["tool_name"]]
            result = await fn(
                session_id=payload.get("session_id", "mcp-transport-session"),
                project_id=payload.get("project_id", "Ageix_Test"),
                arguments=payload.get("arguments", {}),
                request=request,
            )
            return JSONResponse(result)

        app = Starlette(routes=[Route("/", root, methods=["GET"]), Route("/call", call, methods=["POST"])])
        app.lifespan = None
        return app


def _install_fake_fastmcp(monkeypatch) -> None:
    REGISTERED_TOOLS.clear()
    fastmcp_module = types.ModuleType("fastmcp")
    fastmcp_module.FastMCP = FakeFastMCP
    dependencies_module = types.ModuleType("fastmcp.dependencies")
    dependencies_module.CurrentRequest = lambda: None
    monkeypatch.setitem(sys.modules, "fastmcp", fastmcp_module)
    monkeypatch.setitem(sys.modules, "fastmcp.dependencies", dependencies_module)


def _seed(tmp_path: Path, *, allowed_capabilities: list[str] | None = None) -> None:
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
            "allowed_capabilities": allowed_capabilities or ["identity.current", "ageix.health", "governance.status", "audit.recent", "capabilities.list"],
        }],
    }), encoding="utf-8")


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    _install_fake_fastmcp(monkeypatch)
    from web.app import create_app

    app = create_app(repo_root=tmp_path)
    app.dependency_overrides[get_repo_root] = lambda: tmp_path
    return TestClient(app)


def _headers(token: str = "dev-ageix-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_mcp_transport_available(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    response = _client(tmp_path, monkeypatch).get("/mcp/", headers=_headers())

    assert response.status_code == 200
    assert response.json()["transport"] == "fastmcp"


def test_mcp_transport_requires_auth(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    response = _client(tmp_path, monkeypatch).get("/mcp/")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_mcp_transport_discovery(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    response = _client(tmp_path, monkeypatch).get("/mcp/", headers=_headers())

    tools = set(response.json()["tools"])
    assert "ageix_identity_current" in tools
    assert "ageix_validation_scenarios_list" not in tools


def test_mcp_transport_execution(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    response = _client(tmp_path, monkeypatch).post("/mcp/call", headers=_headers(), json={
        "tool_name": "ageix_identity_current",
        "session_id": "transport-exec",
        "project_id": "Ageix_Test",
        "arguments": {},
    })

    body = response.json()
    assert body["success"] is True
    assert body["result"]["client_id"] == "chatgpt"
    assert body["result"]["agent_id"] == "lex"


def test_mcp_transport_requires_project(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    response = _client(tmp_path, monkeypatch).post("/mcp/call", headers=_headers(), json={
        "tool_name": "ageix_identity_current",
        "session_id": "transport-project",
        "project_id": "current",
        "arguments": {},
    })

    assert response.json()["success"] is False
    assert "project_id_must_be_explicit" in response.text or "project_id_not_authorized_for_token" in response.text


def test_mcp_transport_preserves_governance(tmp_path: Path, monkeypatch):
    _seed(tmp_path, allowed_capabilities=["identity.current"])
    response = _client(tmp_path, monkeypatch).post("/mcp/call", headers=_headers(), json={
        "tool_name": "ageix_proposals_submit",
        "session_id": "transport-governance",
        "project_id": "Ageix_Test",
        "arguments": {"objective": "should not be allowed"},
    })

    body = response.json()
    assert body["success"] is False
    assert body["errors"] == ["capability_not_authorized_for_token"]


def test_mcp_transport_identity_propagation(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    response = _client(tmp_path, monkeypatch).post("/mcp/call", headers=_headers(), json={
        "tool_name": "ageix_identity_current",
        "session_id": "identity-propagation",
        "project_id": "Ageix_Test",
        "arguments": {"agent_id": "admin"},
    })

    body = response.json()
    assert body["success"] is False
    assert body["errors"] == ["identity_fields_not_allowed"]


def test_mcp_transport_audit_record(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    _client(tmp_path, monkeypatch).post("/mcp/call", headers=_headers(), json={
        "tool_name": "ageix_identity_current",
        "session_id": "transport-audit",
        "project_id": "Ageix_Test",
        "arguments": {},
    })

    records = CapabilityAuditService(tmp_path).list_records()
    assert records
    assert records[-1]["client_id"] == "chatgpt"
    assert records[-1]["agent_id"] == "lex"
    assert records[-1]["project_id"] == "Ageix_Test"
