from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.devjob import DevJob, DevJobStatus
from models.devjob_result import DevJobResult
from services.devjob_lifecycle_service import transition


class DevJobRegistryService:
    """Governed registry for DevJob coordination records, per INTENT-0007.

    A DevJob is a governed work assignment description. This registry only
    stores, indexes, and tracks the lifecycle of DevJob records and their
    result submissions; it never performs git operations, mutates a target
    repository, or executes work itself.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.devjob_root = self.repo_root / ".ageix" / "devjobs"
        self.index_path = self.devjob_root / "index.json"

    def create_job(
        self,
        *,
        title: str,
        objective: str,
        instructions: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        allowed_paths: list[str] | None = None,
        prohibited_paths: list[str] | None = None,
        repo_target: str | None = None,
        branch_hint: str | None = None,
        evidence_package_ids: list[str] | None = None,
        work_context_id: str | None = None,
        validation_profile_ids: list[str] | None = None,
        conversation_id: str | None = None,
        handoff_id: str | None = None,
        origin: str = "manual",
        status: DevJobStatus = "draft",
        created_by: str,
        assigned_to: str | None = None,
    ) -> DevJob:
        if not str(title or "").strip():
            raise ValueError("devjob_title_required")
        if not str(objective or "").strip():
            raise ValueError("devjob_objective_required")
        if not str(created_by or "").strip():
            raise ValueError("devjob_created_by_required")
        if status not in ("draft", "assigned"):
            raise ValueError("devjob_initial_status_must_be_draft_or_assigned")
        if status == "assigned" and not str(assigned_to or "").strip():
            raise ValueError("devjob_assigned_status_requires_assigned_to")

        job = DevJob(
            title=str(title),
            objective=str(objective),
            instructions=list(instructions or []),
            acceptance_criteria=list(acceptance_criteria or []),
            allowed_paths=list(allowed_paths or []),
            prohibited_paths=list(prohibited_paths or []),
            repo_target=repo_target,
            branch_hint=branch_hint,
            evidence_package_ids=list(evidence_package_ids or []),
            work_context_id=work_context_id,
            validation_profile_ids=list(validation_profile_ids or []),
            conversation_id=conversation_id,
            handoff_id=handoff_id,
            origin=str(origin or "manual"),
            status=status,
            created_by=str(created_by),
            assigned_to=assigned_to,
        )
        job.lifecycle_history.append({
            "from_status": None,
            "to_status": status,
            "actor_id": job.created_by,
            "actor_role": None,
            "note": "devjob_created",
            "transitioned_at": job.created_at,
        })

        self._ensure_layout()
        job_dir = self._job_dir(job.job_id)
        if job_dir.exists():
            raise ValueError("devjob_id_collision")
        job_dir.mkdir(parents=True, exist_ok=False)
        (job_dir / "results").mkdir(parents=True, exist_ok=True)
        self._write_job_file(job)

        index = self._read_index()
        index.append(job.model_dump())
        self._write_index(index)
        return job

    def get_job(self, job_id: str) -> DevJob:
        return self._require_job(job_id)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        assigned_to: str | None = None,
        created_by: str | None = None,
        repo_target: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        jobs = [DevJob(**item) for item in self._read_index()]
        if status:
            jobs = [job for job in jobs if job.status == status]
        if assigned_to:
            jobs = [job for job in jobs if job.assigned_to == assigned_to]
        if created_by:
            jobs = [job for job in jobs if job.created_by == created_by]
        if repo_target:
            jobs = [job for job in jobs if job.repo_target == repo_target]
        jobs = sorted(jobs, key=lambda job: job.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = jobs[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} devjob(s) returned.",
            "devjobs": [job.to_summary() for job in page],
            "count": len(page),
            "total_count": len(jobs),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {
                "status": status,
                "assigned_to": assigned_to,
                "created_by": created_by,
                "repo_target": repo_target,
            },
        }

    def transition_job(
        self,
        job_id: str,
        target_status: DevJobStatus,
        *,
        actor_id: str | None,
        actor_role: AgentRole,
        note: str = "",
    ) -> DevJob:
        job = self._require_job(job_id)
        transition(job, target_status, actor_id=actor_id, actor_role=actor_role, note=note)
        self._save_job(job)
        return job

    def submit_result(
        self,
        *,
        job_id: str,
        result_summary: str = "",
        status: str = "success",
        public_branch_or_pr: str | None = None,
        branch_name: str | None = None,
        changed_files: list[str] | None = None,
        patch_id: str | None = None,
        artifact_ids: list[str] | None = None,
        validation_run_id: str | None = None,
        validation_notes: str = "",
        submitted_by: str,
        actor_role: AgentRole,
    ) -> dict[str, Any]:
        job = self._require_job(job_id)
        if not str(submitted_by or "").strip():
            raise ValueError("devjob_result_submitted_by_required")
        result = DevJobResult(
            job_id=job_id,
            result_summary=str(result_summary or ""),
            status=status,
            public_branch_or_pr=public_branch_or_pr,
            branch_name=branch_name,
            changed_files=list(changed_files or []),
            patch_id=patch_id,
            artifact_ids=list(artifact_ids or []),
            validation_run_id=validation_run_id,
            validation_notes=str(validation_notes or ""),
            submitted_by=str(submitted_by),
        )
        transition(
            job,
            "submitted",
            actor_id=submitted_by,
            actor_role=actor_role,
            note=f"result_submitted:{result.result_id}",
        )
        self._save_result(job.job_id, result)
        self._save_job(job)
        return {
            "job": job.to_summary(),
            "result": result.to_metadata(),
        }

    def get_result(self, job_id: str, result_id: str) -> DevJobResult:
        path = self._job_dir(job_id) / "results" / f"{result_id}.json"
        if not path.exists():
            raise ValueError("devjob_result_not_found")
        return DevJobResult(**json.loads(path.read_text(encoding="utf-8")))

    def list_results(self, job_id: str) -> list[dict[str, Any]]:
        results_dir = self._job_dir(job_id) / "results"
        if not results_dir.exists():
            return []
        results = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(results_dir.glob("*.json"))]
        return sorted(results, key=lambda item: item.get("submitted_at", ""), reverse=True)

    def delete_job(self, job_id: str) -> None:
        """Removes a DevJob's directory and its index entry.

        Reserved for smoke-test and operational cleanup; this is intentionally
        not exposed as an MCP capability.
        """
        index = self._read_index()
        remaining = [item for item in index if item.get("job_id") != job_id]
        if len(remaining) == len(index):
            raise ValueError("devjob_not_found")
        self._write_index(remaining)
        job_dir = self._job_dir(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir)

    def _job_dir(self, job_id: str) -> Path:
        return self.devjob_root / job_id

    def _ensure_layout(self) -> None:
        self.devjob_root.mkdir(parents=True, exist_ok=True)

    def _require_job(self, job_id: str) -> DevJob:
        for item in self._read_index():
            if item.get("job_id") == job_id:
                return DevJob(**item)
        raise ValueError("devjob_not_found")

    def _save_job(self, job: DevJob) -> None:
        index = self._read_index()
        updated = False
        for i, item in enumerate(index):
            if item.get("job_id") == job.job_id:
                index[i] = job.model_dump()
                updated = True
                break
        if not updated:
            raise ValueError("devjob_not_found")
        self._write_job_file(job)
        self._write_index(index)

    def _write_job_file(self, job: DevJob) -> None:
        job_dir = self._job_dir(job.job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def _save_result(self, job_id: str, result: DevJobResult) -> None:
        results_dir = self._job_dir(job_id) / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        path = results_dir / f"{result.result_id}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_index(self, records: list[dict[str, Any]]) -> None:
        self._ensure_layout()
        payload = json.dumps(records, indent=2, sort_keys=True)
        tmp_path = self.index_path.with_name(self.index_path.name + ".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.index_path)
