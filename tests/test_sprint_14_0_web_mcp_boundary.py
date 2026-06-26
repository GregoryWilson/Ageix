from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from services.project_profile_service import ProjectProfileService
from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService
from web.app import create_app
from web.dependencies import get_repo_root


def _seed_project(tmp_path: Path, project_id: str = "Ageix_Test") -> None:
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_repo_root] = lambda: tmp_path
    return TestClient(app)


def _context(project_id: str = "Ageix_Test") -> dict[str, str]:
    return {
        "session_id": "sprint-14-session",
        "project_id": project_id,
    }


def _mcp_context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="sprint-14-session",
        project_id=project_id,
        provider="openai",
        display_name="Lex",
    )


def test_health_endpoint(tmp_path: Path):
    response = _client(tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json()["result"]["status"] == "ok"


def test_capabilities_endpoint(tmp_path: Path):
    response = _client(tmp_path).get("/capabilities")

    assert response.status_code == 200
    assert response.json()["success"] is True
    ids = {item["capability_id"] for item in response.json()["result"]["capabilities"]}
    assert "proposal.submit" in ids
    assert "consultation.submit" in ids


def test_execute_capability_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", json={
        "context": _context(),
        "capability_id": "ageix.health",
        "arguments": {},
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["system"] == "ageix"


def test_projects_current_requires_explicit_project_id(tmp_path: Path):
    response = _client(tmp_path).get("/projects/current", params={
        "session_id": "sprint-14-session",
        "project_id": "current",
    })

    assert response.status_code == 422


def test_projects_current_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    response = _client(tmp_path).get("/projects/current", params={
        "session_id": "sprint-14-session",
        "project_id": "Ageix_Test",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["project_id"] == "Ageix_Test"


def test_create_proposal_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    response = _client(tmp_path).post("/proposals", json={
        "context": _context(),
        "objective": "Expose governed service boundary.",
        "proposal_type": "architecture",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["proposal"]["project_id"] == "Ageix_Test"
    assert response.json()["result"]["evaluation"]["metadata"]["chair_authoritative"] is True


def test_get_proposal_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    create = _client(tmp_path).post("/proposals", json={
        "context": _context(),
        "objective": "Retrieve governed proposal.",
        "proposal_type": "investigation",
    })
    proposal_id = create.json()["result"]["proposal"]["proposal_id"]

    response = _client(tmp_path).get(f"/proposals/{proposal_id}", params={
        "session_id": "sprint-14-session",
        "project_id": "Ageix_Test",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["proposal_id"] == proposal_id


def test_submit_consultation_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    created = _client(tmp_path).post("/proposals", json={
        "context": _context(),
        "objective": "Needs architecture review.",
        "proposal_type": "architecture",
    })
    proposal_id = created.json()["result"]["proposal"]["proposal_id"]

    response = _client(tmp_path).post("/consultations", json={
        "context": _context(),
        "proposal_id": proposal_id,
        "consultation_type": "architecture_review",
        "arguments": {"summary": "Looks sound.", "confidence": 0.8},
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["proposal_id"] == proposal_id
    assert response.json()["result"]["external_agent_submitted"] is True


def test_get_consultation_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    created = _client(tmp_path).post("/proposals", json={
        "context": _context(),
        "objective": "Needs governance review.",
        "proposal_type": "governance",
    })
    proposal_id = created.json()["result"]["proposal"]["proposal_id"]
    submitted = _client(tmp_path).post("/consultations", json={
        "context": _context(),
        "proposal_id": proposal_id,
        "consultation_type": "governance_review",
    })
    consultation_id = submitted.json()["result"]["consultation_id"]

    response = _client(tmp_path).get(f"/consultations/{consultation_id}", params={
        "session_id": "sprint-14-session",
        "project_id": "Ageix_Test",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["consultation_id"] == consultation_id


def test_audit_recent_endpoint(tmp_path: Path):
    _seed_project(tmp_path)
    _client(tmp_path).post("/capabilities/execute", json={
        "context": _context(),
        "capability_id": "ageix.health",
        "arguments": {},
    })

    response = _client(tmp_path).get("/audit/recent", params={
        "session_id": "sprint-14-session",
        "project_id": "Ageix_Test",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["records"][-1]["capability_id"] == "ageix.health"


def test_web_client_cannot_modify_repo(tmp_path: Path):
    _seed_project(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", json={
        "context": _context(),
        "capability_id": "repository.raw_write",
        "arguments": {"path": "foo.py", "content": "bad"},
    })

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["errors"] == ["external_agents_cannot_modify_repository"]


def test_web_client_cannot_execute_worker(tmp_path: Path):
    _seed_project(tmp_path)
    response = _client(tmp_path).post("/capabilities/execute", json={
        "context": _context(),
        "capability_id": "worker.direct_execute",
        "arguments": {"worker": "devworker"},
    })

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["errors"] == ["external_agents_cannot_directly_execute_workers"]


def test_mcp_service_discovers_stable_tools(tmp_path: Path):
    tools = {item["tool_name"] for item in MCPService(tmp_path).discover_tools()}

    assert "ageix.capabilities.execute" in tools
    assert "ageix.proposals.submit" in tools
    assert "ageix.consultations.submit" in tools
    assert "ageix.validation.scenario.request" in tools


def test_mcp_tool_call_routes_through_governed_capability_execution(tmp_path: Path):
    _seed_project(tmp_path)
    context = _mcp_context()

    response = MCPService(tmp_path).execute_tool("ageix.health", context, {})

    assert response.success is True
    assert response.result["status"] == "ok"
    assert response.governance["chair_authority_preserved"] is True


def test_mcp_reserved_sandbox_tool_is_placeholder_only(tmp_path: Path):
    context = _mcp_context()

    response = MCPService(tmp_path).execute_tool("ageix.validation.scenario.request", context, {"scenario": "pytest"})

    assert response.success is False
    assert response.governance["reason"] == "placeholder_reserved_for_validation_sandbox"
