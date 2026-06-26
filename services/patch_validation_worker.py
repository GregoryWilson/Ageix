from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


@dataclass(frozen=True)
class WorkerContext:
    project_id: str
    agent_id: str = "unknown"
    session_id: str = "unknown"
    metadata: Optional[Dict[str, Any]] = None


class PatchValidationWorker:
    VALID_STATUSES = {"passed", "failed", "error"}

    def __init__(self, *, repo_root: Path | str = ".", patch_root: Path | str = ".ageix/patches", timeout_seconds: int = 30) -> None:
        self.repo_root = Path(repo_root)
        self.patch_root = Path(patch_root)
        self.timeout_seconds = int(timeout_seconds)
        self.validation_root = self.repo_root / ".ageix" / "patch_validations"
        self.index_path = self.validation_root / "index.json"

    def validate(self, *, patch_id: str, context: Optional[WorkerContext] = None) -> Dict[str, Any]:
        started = time.monotonic()
        stdout = ""
        stderr = ""
        exit_code = None
        started_at = self._now()
        try:
            patch_path = self._resolve_patch(patch_id)
            result = subprocess.run(
                ["git", "apply", "--check", str(patch_path)],
                cwd=str(self.repo_root),
                text=True,
                capture_output=True,
                shell=False,
                timeout=self.timeout_seconds,
                check=False,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.returncode
            status = "passed" if result.returncode == 0 else "failed"
            summary = "Patch validated successfully." if status == "passed" else "Patch validation failed."
        except subprocess.TimeoutExpired as exc:
            status = "error"
            summary = "Patch validation timed out."
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        except Exception as exc:
            status = "error"
            summary = str(exc)

        return self._store_result(
            patch_id=patch_id,
            status=status,
            summary=summary,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            context=context,
        )

    def get(self, *, patch_validation_id: str) -> Dict[str, Any]:
        path = self.validation_root / patch_validation_id / "result.json"
        if not path.exists():
            raise KeyError(f"patch validation not found: {patch_validation_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, *, patch_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        rows = self._read_index().get("validations", [])
        if patch_id:
            rows = [row for row in rows if row.get("patch_id") == patch_id]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows = sorted(rows, key=lambda row: row.get("completed_at", ""), reverse=True)
        page = rows[offset : offset + limit]
        return {"validations": page, "count": len(page), "total_count": len(rows), "limit": limit, "offset": offset}

    def _resolve_patch(self, patch_id: str) -> Path:
        if not patch_id or not patch_id.startswith("PATCH-"):
            raise ValueError("patch_id must reference a stored PATCH-* artifact")
        root = self.patch_root.resolve()
        for name in ("patch.diff", "diff.patch"):
            candidate = self.patch_root / patch_id / name
            resolved = candidate.resolve()
            if root != resolved and root not in resolved.parents:
                raise ValueError("patch path escaped patch registry root")
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(f"stored patch diff not found for {patch_id}")

    def _store_result(self, **kwargs: Any) -> Dict[str, Any]:
        self.validation_root.mkdir(parents=True, exist_ok=True)
        validation_id = f"PATCHVAL-{uuid4().hex[:12].upper()}"
        validation_dir = self.validation_root / validation_id
        validation_dir.mkdir()

        stdout = kwargs.pop("stdout") or ""
        stderr = kwargs.pop("stderr") or ""
        record = {
            "patch_validation_id": validation_id,
            "patch_id": kwargs["patch_id"],
            "status": kwargs["status"],
            "summary": kwargs["summary"],
            "artifact_id": None,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
            "exit_code": kwargs.get("exit_code"),
            "started_at": kwargs["started_at"],
            "completed_at": self._now(),
            "duration_ms": kwargs["duration_ms"],
            "metadata": {
                "worker": "PatchValidationWorker",
                "version": "19.6",
                "context": self._context(kwargs.get("context")),
            },
        }
        (validation_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (validation_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        (validation_dir / "result.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

        index = self._read_index()
        index.setdefault("validations", []).append(record)
        self._write_index(index)
        return record

    def _read_index(self) -> Dict[str, Any]:
        if not self.index_path.exists():
            return {"validations": []}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"validations": []}

    def _write_index(self, index: Dict[str, Any]) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.index_path)

    @staticmethod
    def _context(context: Optional[WorkerContext]) -> Dict[str, Any]:
        if context is None:
            return {}
        return {"project_id": context.project_id, "agent_id": context.agent_id, "session_id": context.session_id, "metadata": dict(context.metadata or {})}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
