from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services.patch_validation_worker import PatchValidationWorker, WorkerContext

VALID_PATCH = """diff --git a/demo.txt b/demo.txt
index a29bdeb..c5d8473 100644
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-before
+after
"""

INVALID_PATCH = """diff --git a/demo.txt b/demo.txt
index a29bdeb..c5d8473 100644
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-missing
+after
"""


def init_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ageix@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Ageix Test"], cwd=repo, check=True)
    (repo / "demo.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "demo.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True)


def write_patch(repo: Path, patch_id: str, content: str) -> None:
    patch_dir = repo / ".ageix" / "patches" / patch_id
    patch_dir.mkdir(parents=True, exist_ok=True)
    (patch_dir / "patch.diff").write_text(content, encoding="utf-8")


def test_validation_passes_without_mutating_repo(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write_patch(tmp_path, "PATCH-VALID", VALID_PATCH)
    worker = PatchValidationWorker(repo_root=tmp_path, patch_root=tmp_path / ".ageix" / "patches")
    result = worker.validate(patch_id="PATCH-VALID", context=WorkerContext(project_id="Ageix_Test"))
    assert result["status"] == "passed"
    assert result["patch_validation_id"].startswith("PATCHVAL-")
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "before\n"


def test_validation_failed_for_non_matching_patch(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write_patch(tmp_path, "PATCH-INVALID", INVALID_PATCH)
    worker = PatchValidationWorker(repo_root=tmp_path, patch_root=tmp_path / ".ageix" / "patches")
    result = worker.validate(patch_id="PATCH-INVALID")
    assert result["status"] == "failed"
    assert result["exit_code"] not in (None, 0)
    assert result["stderr_tail"]


def test_validation_errors_for_unknown_patch(tmp_path: Path) -> None:
    init_repo(tmp_path)
    worker = PatchValidationWorker(repo_root=tmp_path, patch_root=tmp_path / ".ageix" / "patches")
    result = worker.validate(patch_id="PATCH-MISSING")
    assert result["status"] == "error"
    assert "not found" in result["summary"]


def test_validation_rejects_raw_patch_input(tmp_path: Path) -> None:
    init_repo(tmp_path)
    worker = PatchValidationWorker(repo_root=tmp_path, patch_root=tmp_path / ".ageix" / "patches")
    result = worker.validate(patch_id="demo.diff")
    assert result["status"] == "error"
    assert "PATCH-*" in result["summary"]


def test_validation_get_and_list(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write_patch(tmp_path, "PATCH-VALID", VALID_PATCH)
    worker = PatchValidationWorker(repo_root=tmp_path, patch_root=tmp_path / ".ageix" / "patches")
    result = worker.validate(patch_id="PATCH-VALID")
    assert worker.get(patch_validation_id=result["patch_validation_id"])["patch_id"] == "PATCH-VALID"
    assert worker.list(patch_id="PATCH-VALID")["total_count"] == 1


def test_validation_timeout_is_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_repo(tmp_path)
    write_patch(tmp_path, "PATCH-TIMEOUT", VALID_PATCH)
    worker = PatchValidationWorker(repo_root=tmp_path, patch_root=tmp_path / ".ageix" / "patches", timeout_seconds=1)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git", "apply", "--check"], timeout=1)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    result = worker.validate(patch_id="PATCH-TIMEOUT")
    assert result["status"] == "error"
    assert "timed out" in result["summary"]
