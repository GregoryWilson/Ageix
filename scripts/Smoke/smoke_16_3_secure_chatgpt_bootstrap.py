from __future__ import annotations

import json
import os
import tempfile
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


def seed(repo_root: Path) -> None:
    ProjectProfileService(repo_root).register_project("Ageix_Test", "Ageix Test", "python", repo_root)
    auth_path = repo_root / ".ageix" / "config" / "auth.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(json.dumps({
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
    }, indent=2), encoding="utf-8")


def make_client(repo_root: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_repo_root] = lambda: repo_root
    return TestClient(app)


def main() -> None:
    print("\n== Smoke 16.3: Secure ChatGPT client bootstrap ==")
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        seed(repo_root)
        client = make_client(repo_root)
        headers = {"Authorization": "Bearer dev-ageix-token"}
        context = {"session_id": "smoke-16-3-session", "project_id": "Ageix_Test"}

        print("\n-- authenticate client --")
        health = client.get("/health", headers=headers).json()
        print(health)
        assert health["success"] is True
        assert health["metadata"]["client_id"] == "chatgpt"

        print("\n-- resolve identity --")
        identity = AuthService(repo_root).authenticate_bearer_token("dev-ageix-token")
        resolved_context = AuthService(repo_root).build_resolved_context(identity, session_id=context["session_id"], project_id=context["project_id"])
        print(resolved_context.model_dump())
        assert resolved_context.client_id == "chatgpt"
        assert resolved_context.agent_id == "lex"

        print("\n-- call identity.current --")
        ident = client.post("/capabilities/execute", headers=headers, json={
            "context": context,
            "capability_id": "identity.current",
            "arguments": {},
        }).json()
        print(ident)
        assert ident["success"] is True
        assert ident["result"]["authenticated"] is True
        assert ident["result"]["agent_id"] == "lex"

        print("\n-- reject caller-supplied identity --")
        rejected = client.post("/capabilities/execute", headers=headers, json={
            "context": {**context, "agent_id": "admin", "client_id": "spoof"},
            "capability_id": "identity.current",
            "arguments": {},
        })
        print({"status_code": rejected.status_code, "body": rejected.json()})
        assert rejected.status_code == 422

        print("\n-- verify project authorization --")
        bad_project = client.post("/capabilities/execute", headers=headers, json={
            "context": {"session_id": "smoke-16-3-session", "project_id": "Other_Project"},
            "capability_id": "identity.current",
            "arguments": {},
        })
        print({"status_code": bad_project.status_code, "body": bad_project.json()})
        assert bad_project.status_code == 403

        print("\n-- verify unauthorized capability denial --")
        denied = client.post("/capabilities/execute", headers=headers, json={
            "context": context,
            "capability_id": "repository.raw_write",
            "arguments": {"path": "bad.py", "content": "nope"},
        }).json()
        print(denied)
        assert denied["success"] is False
        assert denied["errors"] == ["capability_not_authorized_for_token"]

        print("\n-- verify MCP identity alignment --")
        web_result = MCPFacadeService(repo_root).execute_tool("ageix.identity.current", resolved_context, {}).result
        mcp_context = AgeixRequestContext(
            client_id="chatgpt",
            agent_id="lex",
            participant_id="greg",
            session_id=context["session_id"],
            project_id=context["project_id"],
            provider="openai",
            display_name="Lex",
            authentication_method="dev_token",
        )
        mcp_result = MCPFacadeService(repo_root).execute_tool("ageix.identity.current", mcp_context, {}).result
        print({"web": web_result, "mcp": mcp_result})
        assert web_result["client_id"] == mcp_result["client_id"]
        assert web_result["agent_id"] == mcp_result["agent_id"]

        print("\n-- verify audit redaction --")
        audit_blob = json.dumps(CapabilityAuditService(repo_root).list_records())
        print({"records": CapabilityAuditService(repo_root).list_records()[-3:]})
        assert "dev-ageix-token" not in audit_blob
        assert "Authorization" not in audit_blob

        public_url = os.environ.get("AGEIX_PUBLIC_URL")
        public_token = os.environ.get("AGEIX_DEV_AUTH_TOKEN")
        if public_url and public_token:
            import requests
            print("\n-- verify public endpoint authentication --")
            public = requests.get(f"{public_url.rstrip('/')}/health", headers={"Authorization": f"Bearer {public_token}"}, timeout=10)
            print({"status_code": public.status_code, "body": public.text[:500]})
            assert public.status_code == 200
        else:
            print("\n-- public endpoint authentication skipped: set AGEIX_PUBLIC_URL and AGEIX_DEV_AUTH_TOKEN to run --")

    print("\nSmoke 16.3 PASS: secure ChatGPT bootstrap boundary is operational.")


if __name__ == "__main__":
    main()
