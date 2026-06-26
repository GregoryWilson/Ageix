from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.evidence_package import EvidencePackage, EvidencePackageItem, EvidenceProvenance
from services.evidence_package_index_service import EvidencePackageIndexService
from services.artifact_registry_service import ArtifactRegistryService


@dataclass(frozen=True)
class ValidationProfile:
    profile_id: str
    name: str
    profile_type: str
    command: tuple[str, ...]
    timeout_seconds: int
    risk: str
    description: str
    evidence_paths: tuple[str, ...] = ()

    def to_summary(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "type": self.profile_type,
            "risk": self.risk,
            "timeout_seconds": self.timeout_seconds,
            "description": self.description,
            "command_summary": " ".join(self.command),
            "evidence_paths": list(self.evidence_paths),
            "arguments_supported": False,
            "shell_execution": False,
        }


class ValidationOperationsService:
    """Governed async execution lifecycle for approved validation profiles only."""

    TERMINAL_STATUSES = {"PASS", "FAIL", "ERROR", "TIMEOUT"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.run_root = self.repo_root / ".ageix" / "validation_runs"
        self.profiles = self._default_profiles()

    def list_profiles(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        profiles = [profile.to_summary() for profile in self.profiles.values()]
        window = profiles[max(offset, 0): max(offset, 0) + max(limit, 0)]
        return {"summary": f"{len(window)} validation profile(s) returned.", "profiles": window, "count": len(window), "total": len(profiles), "offset": offset}

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        profile = self._require_profile(profile_id)
        return profile.to_summary()

    def start_run(self, *, profile_id: str, agent_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        profile = self._require_profile(profile_id)
        run_id = f"VALRUN-{uuid4().hex[:12].upper()}"
        run_dir = self.run_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        started_at = self._now()
        record = {
            "run_id": run_id,
            "profile_id": profile.profile_id,
            "profile_name": profile.name,
            "status": "RUNNING",
            "started_at": started_at,
            "completed_at": None,
            "duration_seconds": None,
            "timeout_seconds": profile.timeout_seconds,
            "risk": profile.risk,
            "command_summary": " ".join(profile.command),
            "command": list(profile.command),
            "shell_execution": False,
            "arguments_supported": False,
            "pid": None,
            "returncode": None,
            "stdout_path": str(stdout_path.relative_to(self.repo_root)),
            "stderr_path": str(stderr_path.relative_to(self.repo_root)),
            "evidence_package_id": None,
            "artifact_id": None,
            "agent_id": agent_id,
            "session_id": session_id,
            "summary": f"Validation profile {profile.profile_id} started.",
        }
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                list(profile.command),
                cwd=self.repo_root,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                shell=False,
                start_new_session=True,
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()
        record["pid"] = process.pid
        self._write_record(run_id, record)
        return self._public_record(record)

    def status(self, run_id: str) -> dict[str, Any]:
        record = self._load_record(run_id)
        if record.get("status") == "RUNNING":
            record = self._refresh_running_record(record)
        return self._public_record(record)

    def result(self, run_id: str) -> dict[str, Any]:
        record = self.status(run_id)
        stored = self._load_record(run_id)
        stdout_text = self._tail_text(self.repo_root / str(stored.get("stdout_path") or ""))
        stderr_text = self._tail_text(self.repo_root / str(stored.get("stderr_path") or ""))
        return {**record, "stdout_tail": stdout_text, "stderr_tail": stderr_text, "output_truncated": True}

    def history(self, *, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        runs = []
        if self.run_root.exists():
            for record_path in sorted(self.run_root.glob("VALRUN-*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                record = json.loads(record_path.read_text(encoding="utf-8"))
                if record.get("status") == "RUNNING":
                    record = self._refresh_running_record(record)
                runs.append(self._public_record(record))
        window = runs[max(offset, 0): max(offset, 0) + max(limit, 0)]
        return {"summary": f"{len(window)} validation run(s) returned.", "runs": window, "count": len(window), "total": len(runs), "offset": offset}

    def _default_profiles(self) -> dict[str, ValidationProfile]:
        profiles = [
            ValidationProfile(
                profile_id="SMOKE_19_0_REPOSITORY_VISIBILITY",
                name="Sprint 19.0 Repository Visibility Smoke",
                profile_type="smoke",
                command=("python", "scripts/Smoke/smoke_19_0_repository_visibility.py"),
                timeout_seconds=120,
                risk="low",
                description="Run the Sprint 19.0 repository visibility smoke profile.",
                evidence_paths=("scripts/Smoke/smoke_19_0_repository_visibility.py", "tests/test_sprint_19_0_repository_visibility.py"),
            ),
            ValidationProfile(
                profile_id="TEST_19_0_REPOSITORY_VISIBILITY",
                name="Sprint 19.0 Repository Visibility Unit Tests",
                profile_type="pytest",
                command=("python", "-m", "pytest", "tests/test_sprint_19_0_repository_visibility.py", "-q"),
                timeout_seconds=120,
                risk="low",
                description="Run the focused Sprint 19.0 repository visibility tests.",
                evidence_paths=("tests/test_sprint_19_0_repository_visibility.py",),
            ),
            ValidationProfile(
                profile_id="REGRESSION_CORE",
                name="Core Pytest Regression",
                profile_type="regression",
                command=("python", "-m", "pytest", "tests", "-q"),
                timeout_seconds=1800,
                risk="medium",
                description="Run the approved core pytest regression suite asynchronously.",
                evidence_paths=("tests",),
            ),
        ]
        return {profile.profile_id: profile for profile in profiles if self._profile_available(profile)}

    def _profile_available(self, profile: ValidationProfile) -> bool:
        if not profile.command:
            return False
        command_paths = [part for part in profile.command if part.endswith(".py")]
        return all((self.repo_root / path).exists() for path in command_paths)

    def _require_profile(self, profile_id: str) -> ValidationProfile:
        if profile_id not in self.profiles:
            raise ValueError("validation_profile_not_registered")
        return self.profiles[profile_id]

    def _refresh_running_record(self, record: dict[str, Any]) -> dict[str, Any]:
        pid = int(record.get("pid") or 0)
        started_at = datetime.fromisoformat(str(record["started_at"]))
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        timeout_seconds = int(record.get("timeout_seconds") or 0)
        if timeout_seconds and elapsed > timeout_seconds:
            self._terminate_pid(pid)
            return self._complete(record, "TIMEOUT", returncode=None, summary="Validation run exceeded its profile timeout.")
        if self._pid_running(pid):
            self._write_record(str(record["run_id"]), record)
            return record
        returncode = self._best_effort_returncode(record)
        status = "PASS" if returncode == 0 else "FAIL"
        return self._complete(record, status, returncode=returncode, summary=f"Validation run completed with status {status}.")

    def _complete(self, record: dict[str, Any], status: str, *, returncode: int | None, summary: str) -> dict[str, Any]:
        if record.get("status") in self.TERMINAL_STATUSES:
            return record
        completed_at = self._now()
        started_at = datetime.fromisoformat(str(record["started_at"]))
        duration = (datetime.fromisoformat(completed_at) - started_at).total_seconds()
        record.update({"status": status, "completed_at": completed_at, "duration_seconds": round(duration, 3), "returncode": returncode, "summary": summary})
        record["evidence_package_id"] = self._create_evidence_package(record)
        record["artifact_id"] = self._register_validation_artifact(record)
        self._write_record(str(record["run_id"]), record)
        return record

    def _create_evidence_package(self, record: dict[str, Any]) -> str:
        stdout_rel = str(record.get("stdout_path") or "")
        stderr_rel = str(record.get("stderr_path") or "")
        items = []
        for rel, reason in [(stdout_rel, "Validation stdout captured during governed profile execution."), (stderr_rel, "Validation stderr captured during governed profile execution.")]:
            path = self.repo_root / rel
            content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            items.append(EvidencePackageItem(
                path=rel,
                classification="validation",
                relevance_reason=reason,
                retrieval_reason="Generated by validation.run.start lifecycle.",
                content=content[-20000:],
                line_count=len(content.splitlines()),
                returned_line_count=len(content[-20000:].splitlines()),
                excerpted=len(content) > 20000,
                provenance=EvidenceProvenance(retrieval_method="validation_run_artifact", retrieval_source="validation_operations_service", selection_reason=reason),
                metadata={"run_id": record.get("run_id"), "status": record.get("status")},
            ))
        package = EvidencePackage(
            proposal_id=str(record.get("run_id")),
            evidence_plan_id=f"VALPLAN-{record.get('run_id')}",
            objective=f"Validation run evidence for {record.get('profile_id')}",
            intent="governed_validation_run",
            repository_snapshot={"profile_id": record.get("profile_id"), "status": record.get("status"), "returncode": record.get("returncode")},
            visibility_scope={"source": "validation_operations", "run_id": record.get("run_id")},
            validation_evidence=items,
            retrieval_confidence=1.0,
            confidence_reason="Evidence was generated directly by the governed validation runner.",
            requester_identity={"agent_id": record.get("agent_id"), "session_id": record.get("session_id")},
            audit_metadata={"capability_id": "validation.run.start", "run_id": record.get("run_id")},
        )
        package_dir = self.repo_root / ".ageix" / "evidence_packages" / package.package_id
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "package.json").write_text(package.model_dump_json(indent=2), encoding="utf-8")
        EvidencePackageIndexService(self.repo_root).upsert_package(package)
        return package.package_id


    def _register_validation_artifact(self, record: dict[str, Any]) -> str:
        artifact = ArtifactRegistryService(self.repo_root).register_artifact(
            artifact_category="validation",
            artifact_type="validation_output",
            created_by="validation.run",
            source_id=str(record.get("run_id")),
            summary=f"Validation {record.get('profile_id')} completed with status {record.get('status')}.",
            path=self.run_root / str(record.get("run_id")),
            references=[
                {"reference_type": "validation_run", "reference_id": str(record.get("run_id")), "relationship": "generated_by"},
                {"reference_type": "evidence_package", "reference_id": str(record.get("evidence_package_id")), "relationship": "supported_by"},
            ],
            metadata={
                "run_id": record.get("run_id"),
                "profile_id": record.get("profile_id"),
                "profile_name": record.get("profile_name"),
                "status": record.get("status"),
                "returncode": record.get("returncode"),
                "duration_seconds": record.get("duration_seconds"),
                "stdout_path": record.get("stdout_path"),
                "stderr_path": record.get("stderr_path"),
                "evidence_package_id": record.get("evidence_package_id"),
            },
        )
        return str(artifact["artifact_id"])

    def _pid_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        proc_status = Path(f"/proc/{pid}/status")
        if proc_status.exists():
            try:
                for line in proc_status.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("State:") and "Z" in line.split():
                        return False
            except OSError:
                pass
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _best_effort_returncode(self, record: dict[str, Any]) -> int:
        stdout = self._tail_text(self.repo_root / str(record.get("stdout_path") or ""), limit=50000)
        stderr = self._tail_text(self.repo_root / str(record.get("stderr_path") or ""), limit=50000)
        joined = f"{stdout}\n{stderr}"
        if "Smoke" in joined and "PASS" in joined:
            return 0
        if " passed" in joined and " failed" not in joined and "ERROR" not in joined:
            return 0
        return 1

    def _terminate_pid(self, pid: int) -> None:
        if pid <= 0:
            return
        try:
            os.kill(pid, 15)
        except OSError:
            return

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key not in {"pid", "command"}}

    def _load_record(self, run_id: str) -> dict[str, Any]:
        path = self.run_root / run_id / "run.json"
        if not path.exists():
            raise ValueError("validation_run_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_record(self, run_id: str, record: dict[str, Any]) -> None:
        path = self.run_root / run_id / "run.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    def _tail_text(self, path: Path, *, limit: int = 4000) -> str:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
