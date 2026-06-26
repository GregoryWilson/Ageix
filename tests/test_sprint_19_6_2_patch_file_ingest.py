from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services.patch_registry_service import PatchRegistryService
from services.patch_writer_worker import PatchWriterWorker


VALID_PATCH = """diff --git a/demo.txt b/demo.txt
index a29bdeb..c5d8473 100644
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-before
+after
"""


def test_patch_ingest_imports_from_local_export(tmp_path: Path) -> None:
    source_dir = tmp_path / ".ageix" / "artifact_deliveries" / "local_export"
    source_dir.mkdir(parents=True)
    source = source_dir / "change.patch"
    source.write_text(VALID_PATCH, encoding="utf-8")

    result = PatchWriterWorker(tmp_path).import_patch_file(
        patch_name="change.patch",
        source_path=source.relative_to(tmp_path).as_posix(),
        summary="imported patch",
        project_id="Ageix_Test",
        agent_id="lex",
        client_id="chatGPT",
        session_id="test-session",
        metadata={"sprint": "19.6.2"},
    )

    assert result["patch_id"].startswith("PATCH-")
    metadata = PatchRegistryService(tmp_path).metadata(result["patch_id"])
    stored = tmp_path / metadata["patch_path"]
    assert stored.read_text(encoding="utf-8") == VALID_PATCH

    assert metadata["metadata"]["patch_import_source_path"] == ".ageix/artifact_deliveries/local_export/change.patch"
    assert metadata["worker_context"]["worker"] == "PatchWriterWorker"


def test_patch_ingest_rejects_unapproved_source_path(tmp_path: Path) -> None:
    source = tmp_path / "change.patch"
    source.write_text(VALID_PATCH, encoding="utf-8")

    with pytest.raises(ValueError, match="patch_import_source_not_allowed"):
        PatchWriterWorker(tmp_path).import_patch_file(
            patch_name="change.patch",
            source_path=source,
        )


def test_patch_ingest_rejects_non_utf8_patch(tmp_path: Path) -> None:
    source_dir = tmp_path / ".ageix" / "patch_imports"
    source_dir.mkdir(parents=True)
    source = source_dir / "bad.patch"
    source.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(ValueError, match="patch_import_source_must_be_utf8"):
        PatchWriterWorker(tmp_path).import_patch_file(
            patch_name="bad.patch",
            source_path=source,
        )
