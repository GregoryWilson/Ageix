from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from services.patch_registry_service import PatchRegistryService
from services.patch_writer_worker import PatchWriterWorker


PATCH = """diff --git a/demo.txt b/demo.txt
index a29bdeb..c5d8473 100644
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-before
+after
"""


def main() -> int:
    print("== Smoke 19.6.2: Patch file ingest ==")
    repo = Path(tempfile.mkdtemp(prefix="ageix_patch_ingest_smoke_"))
    try:
        export_dir = repo / ".ageix" / "artifact_deliveries" / "local_export"
        export_dir.mkdir(parents=True)
        source = export_dir / "smoke.patch"
        source.write_text(PATCH, encoding="utf-8")

        result = PatchWriterWorker(repo).import_patch_file(
            patch_name="smoke.patch",
            source_path=source.relative_to(repo).as_posix(),
            summary="smoke patch import",
            project_id="Ageix_Test",
            agent_id="lex",
            client_id="chatGPT",
            session_id="smoke_19_6_2",
            metadata={"smoke": True},
        )

        metadata = PatchRegistryService(repo).metadata(result["patch_id"])
        stored = repo / metadata["patch_path"]
        assert stored.read_text(encoding="utf-8") == PATCH
        print(json.dumps({
            "patch_id": result["patch_id"],
            "artifact_id": result["artifact_id"],
            "byte_count": result["byte_count"],
            "source_preserved": True,
        }, indent=2))
        print("Smoke 19.6.2 PASS: server-local patch file imported and stored without JSON patch transport.")
        return 0
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
