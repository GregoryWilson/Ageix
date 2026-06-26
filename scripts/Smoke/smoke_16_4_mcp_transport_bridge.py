from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.capability_audit_service import CapabilityAuditService
from services.project_profile_service import ProjectProfileService
from web.app import create_app
from web.dependencies import get_repo_root


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = "Ageix_Test"
TOKEN = "dev-ageix-token"


def seed() -> None:
    try:
        ProjectProfileService(ROOT).register_project(PROJECT_ID, "Ageix Test", "python", ROOT)
    except Exception as exc:
        if "Project already registered" not in str(exc):
            raise
    path = ROOT / ".ageix" / "config" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "enabled": True,
        "mode": "dev_token",
        "tokens": [{
            "name": "chatgpt-dev",
            "token_value": TOKEN,
            "client_id": "chatgpt",
            "agent_id": "lex",
            "participant_id": "greg",
            "allowed_projects": [PROJECT_ID],
            "allowed_capabilities": ["identity.current", "ageix.health", "audit.recent", "capabilities.list"],
        }],
    }), encoding="utf-8")


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def main() -> None:
    print("\n== Smoke 16.4: MCP transport bridge ==")
    seed()
    app = create_app(repo_root=ROOT)
    app.dependency_overrides[get_repo_root] = lambda: ROOT
    client = TestClient(app)

    print("\n-- unauthorized transport request --")
    unauthorized = client.get("/mcp/")
    print(unauthorized.status_code, unauthorized.text[:200])
    assert unauthorized.status_code == 401

    print("\n-- REST discovery remains governed --")
    discovery = client.get("/mcp/tools", headers=headers()).json()
    print(discovery)
    assert discovery["success"] is True
    assert any(tool["tool_name"] == "ageix.identity.current" for tool in discovery["result"]["tools"])

    print("\n-- governed REST MCP execution --")
    executed = client.post("/mcp/tools/call", headers=headers(), json={
        "context": {"session_id": "smoke-16-4", "project_id": PROJECT_ID},
        "tool_name": "ageix.identity.current",
        "arguments": {},
    }).json()
    print(executed)
    assert executed["success"] is True
    assert executed["result"]["client_id"] == "chatgpt"

    print("\n-- unauthorized capability blocked --")
    denied = client.post("/mcp/tools/call", headers=headers(), json={
        "context": {"session_id": "smoke-16-4", "project_id": PROJECT_ID},
        "tool_name": "ageix.proposals.submit",
        "arguments": {"objective": "should not run"},
    }).json()
    print(denied)
    assert denied["success"] is False
    assert denied["errors"] == ["capability_not_authorized_for_token"]

    print("\n-- audit continuity --")
    records = CapabilityAuditService(ROOT).list_records()
    print(records[-1] if records else {})
    assert records

    print("\nSmoke 16.4 PASS")


if __name__ == "__main__":
    main()
