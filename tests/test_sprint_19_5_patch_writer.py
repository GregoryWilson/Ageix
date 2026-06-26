from __future__ import annotations

from pathlib import Path

import pytest

from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from services.artifact_registry_service import ArtifactRegistryService
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.patch_registry_service import PATCH_MAX_BYTES, PatchRegistryService
from services.patch_writer_worker import PatchWriterWorker


PATCH_TEXT = """diff --git a/services/example.py b/services/example.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/services/example.py
@@ -0,0 +1,2 @@
+def example():
+    return True
"""


def test_patch_writer_stores_patch_and_registers_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = PatchWriterWorker(repo).create_patch(
        patch_name="sprint_19_5.patch",
        patch_content=PATCH_TEXT,
        summary="Adds example file.",
        project_id="Ageix",
        agent_id="lex",
        client_id="chatGPT",
        session_id="S19_5",
    )

    assert result["patch_id"].startswith("PATCH-")
    assert result["artifact_id"].startswith("ART-")
    assert result["validation_status"] == "not_validated"
    assert result["content_sha256"]
    assert result["line_count"] >= 7
    assert result["file_count_estimate"] == 1
    patch_dir = repo / ".ageix" / "patches" / result["patch_id"]
    assert (patch_dir / "patch.diff").read_text(encoding="utf-8") == PATCH_TEXT
    assert (patch_dir / "metadata.json").exists()

    artifact = ArtifactRegistryService(repo).metadata(result["artifact_id"])
    assert artifact["artifact_category"] == "patch"
    assert artifact["artifact_type"] == "patch_package"
    assert artifact["source_id"] == result["patch_id"]
    assert artifact["metadata"]["content_sha256"] == result["content_sha256"]


def test_patch_get_is_metadata_first_and_content_requires_explicit_flag(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = PatchRegistryService(repo)
    created = service.create_patch(
        patch_name="demo.diff",
        patch_content=PATCH_TEXT,
        summary="Demo patch.",
    )

    metadata_only = service.get_patch(created["patch_id"])
    with_content = service.get_patch(created["patch_id"], include_content=True)

    assert metadata_only["patch_id"] == created["patch_id"]
    assert metadata_only["has_content"] is True
    assert "patch_content" not in metadata_only
    assert with_content["patch_content"] == PATCH_TEXT


def test_patch_create_rejects_non_patch_and_oversized_payload(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = PatchRegistryService(repo)

    with pytest.raises(ValueError, match="patch_content_must_look_like_unified_diff"):
        service.create_patch(patch_name="bad.patch", patch_content="print('nope')\n")

    oversized = "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n" + "+" + ("x" * PATCH_MAX_BYTES)
    with pytest.raises(ValueError, match="patch_content_exceeds_1mb_limit"):
        service.create_patch(patch_name="huge.patch", patch_content=oversized)


def test_duplicate_patch_content_is_allowed_with_same_hash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = PatchRegistryService(repo)

    first = service.create_patch(patch_name="one.patch", patch_content=PATCH_TEXT)
    second = service.create_patch(patch_name="two.patch", patch_content=PATCH_TEXT)

    assert first["patch_id"] != second["patch_id"]
    assert first["content_sha256"] == second["content_sha256"]
    listed = service.list_patches()
    assert listed["total_count"] == 2


def test_patch_capabilities_are_registered_executable_and_audited(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    registry = CapabilityRegistryService(repo)
    execution = CapabilityExecutionService(repo)

    assert registry.exists("patch.create")
    assert registry.exists("patch.list")
    assert registry.exists("patch.get")
    assert registry.exists("patch.metadata")

    created = execution.execute(CapabilityRequest(
        capability_id="patch.create",
        session_id="S19_5",
        agent_id="lex",
        arguments={
            "patch_name": "capability.patch",
            "patch_content": PATCH_TEXT,
            "summary": "Capability-created patch.",
            "client_id": "chatGPT",
        },
    ))
    assert created.success is True
    patch_id = created.result["patch_id"]
    fetched = execution.execute(CapabilityRequest(
        capability_id="patch.get",
        session_id="S19_5",
        agent_id="lex",
        arguments={"patch_id": patch_id},
    ))
    fetched_with_content = execution.execute(CapabilityRequest(
        capability_id="patch.get",
        session_id="S19_5",
        agent_id="lex",
        arguments={"patch_id": patch_id, "include_content": True},
    ))
    listed = execution.execute(CapabilityRequest(
        capability_id="patch.list",
        session_id="S19_5",
        agent_id="lex",
        arguments={"limit": 5},
    ))

    assert fetched.success is True
    assert "patch_content" not in fetched.result
    assert fetched_with_content.result["patch_content"] == PATCH_TEXT
    assert listed.result["total_count"] == 1
    records = CapabilityAuditService(repo).list_records()
    assert records[-1]["capability_id"] == "patch.list"
    assert records[-1]["success"] is True


def test_patch_mcp_tools_are_discoverable() -> None:
    registry = MCPToolRegistry()
    tools = {tool["tool_name"]: tool for tool in registry.discover(category="patch")}

    assert "ageix.patch.create" in tools
    assert "ageix.patch.list" in tools
    assert "ageix.patch.get" in tools
    assert "ageix.patch.metadata" in tools
    assert tools["ageix.patch.create"]["capability_id"] == "patch.create"
    assert "patch_content" in tools["ageix.patch.create"]["input_schema"]["properties"]
