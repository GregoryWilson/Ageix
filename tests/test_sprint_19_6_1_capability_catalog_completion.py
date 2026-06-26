from __future__ import annotations

from ageix_mcp.tool_definitions import MCP_TOOL_DEFINITIONS
from services.capabilities.patch_capabilities import register_capabilities


def _tool_by_capability() -> dict[str, object]:
    return {tool.capability_id: tool for tool in MCP_TOOL_DEFINITIONS}


def test_catalog_exposes_missing_phase_17_19_capability_tools() -> None:
    tools = _tool_by_capability()
    for capability_id in (
        "evidence.request",
        "evidence.proposal.submit",
        "governance.status",
        "agent.list",
        "agent.profile",
        "patch.validate",
        "patch.validation.get",
        "patch.validation.list",
        "patch.ingest",
    ):
        assert capability_id in tools
        assert tools[capability_id].description


def test_catalog_guides_repository_patch_and_artifact_workflows() -> None:
    tools = _tool_by_capability()
    assert "ageix.patch.validate" in tools["patch.create"].recommended_next_tools
    assert "ageix.artifact.push" in tools["repo.archive.create"].recommended_next_tools
    assert "ageix.patch.validation.list" in tools["patch.metadata"].related_tools
    assert "inspect_code" in tools["evidence.request"].documentation["intent_tags"]
    assert "package_repository" in tools["repo.archive.create"].documentation["intent_tags"]


def test_patch_capability_plugin_registers_validation_handlers(tmp_path) -> None:
    registered = {definition.capability_id: handler for definition, handler in register_capabilities(tmp_path)}
    for capability_id in ("patch.validate", "patch.validation.get", "patch.validation.list"):
        assert capability_id in registered
        assert callable(registered[capability_id])
