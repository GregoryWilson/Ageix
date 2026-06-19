from __future__ import annotations

from pathlib import Path

import pytest

from mcp.facade_service import MCPFacadeService
from mcp.tool_definitions import MCPToolDefinition
from mcp.tool_registry import MCPToolRegistry
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext
from services.project_profile_service import ProjectProfileService


def _seed_project(tmp_path: Path, project_id: str = "Ageix_Test") -> None:
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def _context(project_id: str = "Ageix_Test") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="greg",
        session_id="sprint-15-session",
        project_id=project_id,
    )


def test_mcp_server_startup(tmp_path: Path):
    service = MCPFacadeService(tmp_path)

    assert service.discover_tools()
    assert service.tool_registry.get("ageix.health") is not None


def test_mcp_tool_registration():
    registry = MCPToolRegistry(definitions=[])
    definition = MCPToolDefinition(
        name="ageix.example.tool",
        capability_id="example.tool",
        category="example",
        description="Example extensibility test tool.",
    )

    registered = registry.register(definition)

    assert registered == definition
    assert registry.get("ageix.example.tool") == definition
    assert registry.map_capability("ageix.example.tool") == "example.tool"


def test_mcp_tool_registration_requires_ageix_prefix():
    registry = MCPToolRegistry(definitions=[])

    with pytest.raises(ValueError, match="mcp_tool_name_must_use_ageix_prefix"):
        registry.register(MCPToolDefinition(
            name="bad.tool",
            capability_id="bad.tool",
            category="bad",
            description="Bad tool.",
        ))


def test_mcp_tool_discovery(tmp_path: Path):
    tools = MCPFacadeService(tmp_path).discover_tools()
    names = {item["tool_name"] for item in tools}

    assert "ageix.health" in names
    assert "ageix.capabilities.execute" in names
    assert "ageix.proposals.submit" in names
    assert "ageix.validation.scenario.request" in names
    validation = next(item for item in tools if item["tool_name"] == "ageix.validation.scenario.request")
    assert validation["placeholder"] is True
    assert validation["experimental"] is True
    assert validation["capability_id"] == "validation.scenario.request"


def test_mcp_tool_execution(tmp_path: Path):
    _seed_project(tmp_path)

    response = MCPFacadeService(tmp_path).execute_tool("ageix.health", _context(), {})

    assert response.success is True
    assert response.result["system"] == "ageix"
    assert response.governance["chair_authority_preserved"] is True
    assert response.metadata["tool_name"] == "ageix.health"


def test_mcp_governance_preserved(tmp_path: Path):
    _seed_project(tmp_path)

    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.capabilities.execute",
        _context(),
        {"capability_id": "governance.status", "arguments": {}},
    )

    assert response.success is True
    assert response.result["chair_approval_required"] is True
    assert response.governance["chair_authority_preserved"] is True


def test_mcp_repository_denial(tmp_path: Path):
    _seed_project(tmp_path)

    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.capabilities.execute",
        _context(),
        {"capability_id": "repository.raw_write", "arguments": {"path": "bad.py", "content": "nope"}},
    )

    assert response.success is False
    assert response.errors == ["external_agents_cannot_modify_repository"]
    assert response.governance["decision"] == "denied"
    assert response.governance["chair_authority_preserved"] is True


def test_mcp_worker_denial(tmp_path: Path):
    _seed_project(tmp_path)

    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.capabilities.execute",
        _context(),
        {"capability_id": "worker.direct_execute", "arguments": {"worker": "devworker"}},
    )

    assert response.success is False
    assert response.errors == ["external_agents_cannot_directly_execute_workers"]
    assert response.governance["decision"] == "denied"


def test_mcp_context_mapping(tmp_path: Path):
    _seed_project(tmp_path)
    context = _context()

    MCPFacadeService(tmp_path).execute_tool("ageix.health", context, {})
    record = CapabilityAuditService(tmp_path).list_records()[-1]

    assert record["client_id"] == "chatgpt"
    assert record["agent_id"] == "lex"
    assert record["participant_id"] == "greg"
    assert record["session_id"] == "sprint-15-session"
    assert record["project_id"] == "Ageix_Test"


def test_mcp_project_required():
    with pytest.raises(ValueError):
        AgeixRequestContext(
            client_id="chatgpt",
            agent_id="lex",
            session_id="sprint-15-session",
            project_id="current",
        )


def test_mcp_audit_capture(tmp_path: Path):
    _seed_project(tmp_path)

    MCPFacadeService(tmp_path).execute_tool("ageix.health", _context(), {})
    records = CapabilityAuditService(tmp_path).list_records()

    assert records
    assert records[-1]["capability_id"] == "ageix.health"


def test_mcp_placeholders_are_discoverable_with_friendly_errors(tmp_path: Path):
    response = MCPFacadeService(tmp_path).execute_tool(
        "ageix.validation.scenario.request",
        _context(),
        {"scenario": "pytest"},
    )

    assert response.success is False
    assert response.errors == ["validation sandbox not yet implemented"]
    assert response.metadata["placeholder"] is True
    assert response.metadata["capability_id"] == "validation.scenario.request"


def test_mcp_transport_cannot_bypass_capability_execution(tmp_path: Path):
    _seed_project(tmp_path)
    service = MCPFacadeService(tmp_path)

    response = service.execute_tool("ageix.health", _context(), {})
    audit_records = CapabilityAuditService(tmp_path).list_records()

    assert response.success is True
    assert audit_records[-1]["capability_id"] == "ageix.health"
    assert audit_records[-1]["reason"] == "executed"
