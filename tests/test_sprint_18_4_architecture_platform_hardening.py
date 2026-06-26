from __future__ import annotations

import json
from pathlib import Path

import pytest

from ageix_mcp.facade_service import MCPFacadeService
from services.auth_service import AuthService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext
from services.project_registry_service import ProjectRegistryService


def _context(project_id: str = "Ageix") -> AgeixRequestContext:
    return AgeixRequestContext(
        client_id="chatGPT",
        agent_id="lex",
        provider="chatGPT",
        session_id="session-18-4",
        project_id=project_id,
        participant_id="chatgpt",
        authentication_method="dev_token",
    )


def test_legacy_auth_config_normalizes_to_modern_token_record(tmp_path: Path) -> None:
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)
    token = "legacy-token-18-4"
    (config_dir / "auth.json").write_text(json.dumps({
        "auth_enabled": True,
        "dev_token": token,
        "allowed_projects": ["Ageix_Test", "Ageix"],
        "allowed_capabilities": ["architecture.review.submit", "architecture.baseline.validate"],
        "oauth": {"enabled": True, "issuer": "https://auth.example/realms/ageix", "jwks_uri": "https://auth.example/certs"},
    }), encoding="utf-8")

    service = AuthService(tmp_path)
    identity = service.authenticate_bearer_token(token)

    assert service.is_enabled() is True
    assert service.config["mode"] == "hybrid"
    assert service.config["tokens"][0]["token_value"] == token
    assert identity.auth_enabled is True
    assert identity.client_id == "chatgpt"
    assert identity.agent_id == "lex"
    assert identity.allowed_projects == ["Ageix_Test", "Ageix"]
    assert identity.allowed_capabilities == ["architecture.review.submit", "architecture.baseline.validate"]


def test_modern_auth_config_still_works(tmp_path: Path) -> None:
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)
    token = "modern-token-18-4"
    (config_dir / "auth.json").write_text(json.dumps({
        "enabled": True,
        "mode": "dev_token",
        "tokens": [{
            "name": "modern",
            "token_value": token,
            "client_id": "chatgpt",
            "agent_id": "lex",
            "allowed_projects": ["Ageix"],
            "allowed_capabilities": ["*"],
        }],
    }), encoding="utf-8")

    identity = AuthService(tmp_path).authenticate_bearer_token(token)

    assert identity.auth_enabled is True
    assert identity.allowed_projects == ["Ageix"]
    assert identity.allowed_capabilities == ["*"]


def test_official_ageix_project_is_seeded_without_removing_ageix_test(tmp_path: Path) -> None:
    registry = ProjectRegistryService(tmp_path)
    registry.register_project(
        project_id="Ageix_Test",
        name="Ageix Test",
        project_type="python",
        root_path=tmp_path,
        metadata={"purpose": "sandbox"},
    )

    result = registry.ensure_official_ageix_project()
    projects = {project["project_id"]: project for project in registry.list_projects()}

    assert result["seeded"] is True
    assert "Ageix" in projects
    assert "Ageix_Test" in projects
    assert projects["Ageix"]["project_role"] == "system_of_record"
    assert projects["Ageix"]["metadata"]["official"] is True
    assert (tmp_path / ".ageix" / "projects" / "Ageix" / "project_profile.json").exists()


def test_architecture_baseline_validation_uses_registry_and_health(tmp_path: Path) -> None:
    ProjectRegistryService(tmp_path).ensure_official_ageix_project()
    architecture = ArchitectureRegistryService(tmp_path)
    architecture.seed_official_ageix_architecture()

    validation = architecture.validate_baseline(project_id="Ageix")

    assert validation["validation_source"] == "architecture_registry_plus_health"
    assert validation["deterministic"] is True
    assert validation["repository_wide_discovery_performed"] is False
    assert validation["missing_paths"] == []
    assert validation["status"] in {"partial", "complete_current_state"}
    if validation["status"] == "partial":
        assert validation["explanations"]


def test_architecture_baseline_validation_reports_partial_with_explanation(tmp_path: Path) -> None:
    architecture = ArchitectureRegistryService(tmp_path)
    architecture.create_node(
        project_id="Ageix",
        architecture_id="ARCH-AGEIX-PROJECT",
        name="Ageix",
        node_key="Ageix",
        path="Ageix",
        node_type="project",
        description="Only the root is registered.",
    )

    validation = architecture.validate_baseline(project_id="Ageix")

    assert validation["status"] == "partial"
    assert "Ageix.MCPPlatform" in validation["missing_paths"]
    assert any(item.startswith("missing_expected_architecture_path:") for item in validation["explanations"])


def test_mcp_exposes_baseline_validation_and_live_review_flow(tmp_path: Path) -> None:
    ProjectRegistryService(tmp_path).ensure_official_ageix_project()
    architecture = ArchitectureRegistryService(tmp_path)
    architecture.seed_official_ageix_architecture()
    facade = MCPFacadeService(tmp_path)
    tools = {tool["tool_name"] for tool in facade.discover_tools(category="architecture")}

    assert "ageix.architecture.baseline.validate" in tools

    validation = facade.execute_tool("ageix.architecture.baseline.validate", _context(), {"project_id": "Ageix"})
    assert validation.success is True
    assert validation.result["status"] in {"partial", "complete_current_state"}

    review_paths = ["Ageix", "Ageix.MCPPlatform", "Ageix.Architecture"]
    reviews = []
    for path in review_paths:
        response = facade.execute_tool("ageix.architecture.review.submit", _context(), {
            "path": path,
            "summary": f"18.4 live-style review for {path}.",
            "rationale": "Validate external architect review write flow during architecture platform hardening.",
            "no_findings": path != "Ageix.Architecture",
            "metadata": {"sprint": "18.4", "target": path},
        })
        assert response.success is True
        reviews.append(response.result)

    finding = facade.execute_tool("ageix.architecture.finding.submit", _context(), {
        "review_id": reviews[-1]["review_id"],
        "path": "Ageix.Architecture",
        "severity": "informational",
        "category": "requires_additional_discovery",
        "summary": "Architecture baseline hardening should continue to validate live MCP workflows.",
        "rationale": "This finding records the need for continued live validation without judging architecture quality.",
    })
    assert finding.success is True

    challenge = facade.execute_tool("ageix.architecture.challenge.submit", _context(), {
        "path": "Ageix.Architecture",
        "finding_id": finding.result["finding_id"],
        "challenge_summary": "Architecture hardening should keep operational validation close to architecture registry data.",
        "context": "Sprint 18 added registry, health, and review capabilities; 18.4 validates operational trust.",
        "intent": "Keep architecture artifacts trustworthy before future project-system-of-record work.",
        "rationale": "Operational review evidence should remain linked to governed architecture artifacts.",
        "proposed_direction": "Record live MCP validation notes and runbook references in architecture metadata through proposal governance.",
    })
    assert challenge.success is True

    revision = facade.execute_tool("ageix.architecture.revision.propose", _context(), {
        "path": "Ageix.Architecture",
        "challenge_id": challenge.result["challenge_id"],
        "objective": "Propose architecture metadata updates documenting 18.4 platform hardening validation.",
        "proposed_changes": {
            "metadata": {
                "last_hardening_sprint": "18.4",
                "live_mcp_validation": True,
            }
        },
        "metadata": {"sprint": "18.4"},
    })
    assert revision.success is True
    assert revision.result["linked_proposal_id"].startswith("PROP-")
    assert revision.result["metadata"]["proposal_system_reused"] is True
    assert revision.result["metadata"]["direct_registry_mutation"] is False


def test_operations_runbook_exists() -> None:
    runbook = Path("docs/runbooks/ageix_service_operations.md")
    assert runbook.exists()
    text = runbook.read_text(encoding="utf-8")
    assert "Start" in text
    assert "Stop" in text
    assert "Restart" in text
    assert "MCP publication" in text
