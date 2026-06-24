from __future__ import annotations

import pprint
from pathlib import Path
from tempfile import TemporaryDirectory

from models.capability_request import CapabilityRequest
from services.artifact_registry_service import ArtifactRegistryService
from services.capability_execution_service import CapabilityExecutionService


PATCH_TEXT = """diff --git a/services/example.py b/services/example.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/services/example.py
@@ -0,0 +1,2 @@
+def example():
+    return True
"""


def main() -> None:
    print("== Smoke 19.5: governed patch writer ==")
    with TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        execution = CapabilityExecutionService(repo)
        created = execution.execute(CapabilityRequest(
            capability_id="patch.create",
            session_id="S19_5",
            agent_id="lex",
            arguments={
                "patch_name": "smoke_19_5.patch",
                "patch_content": PATCH_TEXT,
                "summary": "Smoke patch writer package.",
                "client_id": "chatGPT",
            },
        ))
        patch_id = created.result["patch_id"]
        artifact_id = created.result["artifact_id"]
        metadata = execution.execute(CapabilityRequest(
            capability_id="patch.metadata",
            session_id="S19_5",
            agent_id="lex",
            arguments={"patch_id": patch_id},
        ))
        fetched = execution.execute(CapabilityRequest(
            capability_id="patch.get",
            session_id="S19_5",
            agent_id="lex",
            arguments={"patch_id": patch_id},
        ))
        fetched_content = execution.execute(CapabilityRequest(
            capability_id="patch.get",
            session_id="S19_5",
            agent_id="lex",
            arguments={"patch_id": patch_id, "include_content": True},
        ))
        listed = execution.execute(CapabilityRequest(
            capability_id="patch.list",
            session_id="S19_5",
            agent_id="lex",
            arguments={"limit": 10},
        ))
        artifact = ArtifactRegistryService(repo).metadata(artifact_id)
        summary = {
            "patch_id": patch_id,
            "artifact_id": artifact_id,
            "status": created.result["status"],
            "validation_status": created.result["validation_status"],
            "line_count": created.result["line_count"],
            "file_count_estimate": created.result["file_count_estimate"],
            "metadata_has_worker_context": bool(metadata.result.get("worker_context")),
            "default_content_hidden": "patch_content" not in fetched.result,
            "explicit_content_returned": fetched_content.result.get("patch_content") == PATCH_TEXT,
            "artifact_category": artifact["artifact_category"],
            "artifact_type": artifact["artifact_type"],
            "listed_count": listed.result["total_count"],
        }
        pprint.pprint(summary)
        assert created.success is True
        assert metadata.success is True
        assert fetched.success is True
        assert fetched_content.success is True
        assert listed.success is True
        assert summary["status"] == "stored"
        assert summary["validation_status"] == "not_validated"
        assert summary["metadata_has_worker_context"] is True
        assert summary["default_content_hidden"] is True
        assert summary["explicit_content_returned"] is True
        assert summary["artifact_category"] == "patch"
        assert summary["artifact_type"] == "patch_package"
        assert summary["listed_count"] == 1
    print("Smoke 19.5 PASS: PatchWriter stored a governed patch package, registered a patch artifact, preserved metadata-first retrieval, and exposed explicit content retrieval only when requested.")


if __name__ == "__main__":
    main()
