from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from services.patch_validation_worker import PatchValidationWorker, WorkerContext

PATCH = """diff --git a/demo.txt b/demo.txt
index a29bdeb..c5d8473 100644
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-before
+after
"""


def main() -> int:
    print("== Smoke 19.6: Patch validation worker ==")
    repo = Path(tempfile.mkdtemp(prefix="ageix_patchval_smoke_"))
    try:
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "ageix@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Ageix Smoke"], cwd=repo, check=True)
        (repo / "demo.txt").write_text("before\n", encoding="utf-8")
        subprocess.run(["git", "add", "demo.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True)

        patch_id = "PATCH-SMOKE196"
        patch_dir = repo / ".ageix" / "patches" / patch_id
        patch_dir.mkdir(parents=True)
        (patch_dir / "patch.diff").write_text(PATCH, encoding="utf-8")

        worker = PatchValidationWorker(repo_root=repo, patch_root=repo / ".ageix" / "patches")
        result = worker.validate(patch_id=patch_id, context=WorkerContext(project_id="Ageix_Test", agent_id="lex", session_id="smoke_19_6"))
        assert result["status"] == "passed", result
        assert worker.get(patch_validation_id=result["patch_validation_id"])["patch_id"] == patch_id
        assert worker.list(patch_id=patch_id)["total_count"] == 1
        assert (repo / "demo.txt").read_text(encoding="utf-8") == "before\n"
        print(f"Smoke 19.6 PASS: {result['patch_validation_id']} passed and repository was not mutated.")
        return 0
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
