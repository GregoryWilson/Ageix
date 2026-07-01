from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.devjob import DevJob, DevJobStatus
from models.devjob_event import DevJobEvent, DevJobEventType
from models.devjob_result import DevJobResult
from services.devjob_lifecycle_service import (
    ALLOWED_TRANSITIONS,
    GOVERNANCE_ROLES,
    authorize_transition,
    is_greg,
    transition,
    validate_assignment_fields,
)


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
        if target_status == "completed":
            # Authorize before evaluating completion requirements so an
            # unauthorized actor is rejected on authority, not on the gate.
            if target_status not in ALLOWED_TRANSITIONS.get(job.status, set()):
                raise ValueError(f"invalid_devjob_state_transition_{job.status}_to_{target_status}")
            authorize_transition(job, target_status, actor_id=actor_id, actor_role=actor_role)
            self._validate_completion_requirements(job)
        transition(job, target_status, actor_id=actor_id, actor_role=actor_role, note=note)
        self._save_job(job)
        return job

    def assign_job(
        self,
        job_id: str,
        *,
        work_context_id: str | None = None,
        acceptance_criteria: list[str] | None = None,
        allowed_paths: list[str] | None = None,
        prohibited_paths: list[str] | None = None,
        instructions: list[str] | None = None,
        assigned_to: str | None = None,
        actor_id: str | None,
        actor_role: AgentRole,
        note: str = "",
    ) -> DevJob:
        """Moves a draft DevJob to assigned, per INTENT-0007 Phase 2.

        Requires non-empty acceptance criteria, allowed paths, prohibited paths,
        and an assigned worker. A Work Context is optional at assignment and is
        required only at the DevWorker execution/load-context boundary.
        """
        job = self._require_job(job_id)
        if job.status != "draft":
            raise ValueError("devjob_assign_requires_draft_status")
        if work_context_id is not None:
            job.work_context_id = work_context_id
        if acceptance_criteria is not None:
            job.acceptance_criteria = list(acceptance_criteria)
        if allowed_paths is not None:
            job.allowed_paths = list(allowed_paths)
        if prohibited_paths is not None:
            job.prohibited_paths = list(prohibited_paths)
        if instructions is not None:
            job.instructions = list(instructions)
        if assigned_to is not None:
            job.assigned_to = assigned_to
        validate_assignment_fields(job)
        transition(job, "assigned", actor_id=actor_id, actor_role=actor_role, note=note or "devjob_assigned")
        self._save_job(job)
        return job

    def revise_scope(
        self,
        job_id: str,
        *,
        reason: str,
        evidence_package_ids: list[str],
        instructions: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        allowed_paths: list[str] | None = None,
        prohibited_paths: list[str] | None = None,
        actor_id: str | None,
        actor_role: AgentRole,
    ) -> DevJob:
        """Records an evidence-gated scope revision. Core identity fields are
        never touched; the prior values are preserved in the append-only event
        log (via the Sprint 21.1/21.5 event API) rather than edited away."""
        job = self._require_job(job_id)
        if job.status not in ("assigned", "in_progress", "blocked"):
            raise ValueError("devjob_scope_revision_not_applicable_from_status")
        if not str(reason or "").strip():
            raise ValueError("devjob_scope_revision_requires_reason")
        if not evidence_package_ids:
            raise ValueError("devjob_scope_revision_requires_evidence")
        if not (is_greg(actor_id) or actor_role in GOVERNANCE_ROLES or actor_id == job.created_by):
            raise ValueError("devjob_scope_revision_requires_creator_or_governance")

        proposed = {
            "instructions": instructions,
            "acceptance_criteria": acceptance_criteria,
            "allowed_paths": allowed_paths,
            "prohibited_paths": prohibited_paths,
        }
        changed_fields = {key: list(value) for key, value in proposed.items() if value is not None}
        if not changed_fields:
            raise ValueError("devjob_scope_revision_requires_at_least_one_field")
        before = {key: list(getattr(job, key)) for key in changed_fields}
        for key, value in changed_fields.items():
            setattr(job, key, value)
        job.evidence_package_ids = list(dict.fromkeys([*job.evidence_package_ids, *evidence_package_ids]))
        job.updated_at = self._now()
        self._save_job(job)
        self.append_event(
            job_id=job.job_id, event_type="scope_revision", reason=str(reason),
            actor_id=str(actor_id or ""), actor_role=actor_role,
            metadata={
                "evidence_package_ids": list(evidence_package_ids),
                "before": before, "after": changed_fields,
            },
        )
        return self._require_job(job.job_id)

    def submit_review(
        self,
        job_id: str,
        *,
        decision: str,
        reviewer_notes: str = "",
        actor_id: str | None,
        actor_role: AgentRole,
    ) -> DevJob:
        """Formal review over a submitted DevJob. Approval -> reviewed; declining
        a submission requires reviewer_notes and sends the job to declined."""
        job = self._require_job(job_id)
        if decision not in ("approved", "changes_requested"):
            raise ValueError("devjob_review_invalid_decision")
        target_status: DevJobStatus = "reviewed" if decision == "approved" else "declined"
        transition(job, target_status, actor_id=actor_id, actor_role=actor_role, note=reviewer_notes)
        self._save_job(job)
        self.append_event(
            job_id=job.job_id, event_type="review_submitted", reason=str(reviewer_notes or ""),
            actor_id=str(actor_id or ""), actor_role=actor_role,
            metadata={"decision": decision, "reviewer_notes": str(reviewer_notes or "")},
        )
        return self._require_job(job.job_id)

    def attach_sync(
        self,
        job_id: str,
        *,
        branch: str | None = None,
        pr_reference: str | None = None,
        commit_sha: str | None = None,
        note: str = "",
        actor_id: str | None,
        actor_role: AgentRole,
    ) -> DevJob:
        """Records a git synchronization reference by reference only. Never
        touches the target repository."""
        job = self._require_job(job_id)
        if not (branch or pr_reference or commit_sha):
            raise ValueError("devjob_sync_attach_requires_reference")
        is_assigned_devworker = actor_role.value == AgentRole.CLAUDE_CODE.value and actor_id == job.assigned_to
        if not (is_greg(actor_id) or actor_role in GOVERNANCE_ROLES or is_assigned_devworker):
            raise ValueError("devjob_sync_attach_requires_assigned_devworker_or_governance")
        self.append_event(
            job_id=job.job_id, event_type="git_sync_attached", reason=str(note or ""),
            actor_id=str(actor_id or ""), actor_role=actor_role,
            metadata={"branch": branch, "pr_reference": pr_reference, "commit_sha": commit_sha},
        )
        job.updated_at = self._now()
        self._save_job(job)
        return self._require_job(job.job_id)

    def record_validation_waiver(
        self,
        job_id: str,
        *,
        reason: str,
        actor_id: str | None,
        actor_role: AgentRole,
    ) -> DevJob:
        """Records a governed waiver of the validation-attached completion gate.
        Restricted to Greg/governance; does not run or skip validation itself."""
        job = self._require_job(job_id)
        if not str(reason or "").strip():
            raise ValueError("devjob_validation_waiver_requires_reason")
        if not (is_greg(actor_id) or actor_role in GOVERNANCE_ROLES):
            raise ValueError("devjob_validation_waiver_requires_governance")
        self.append_event(
            job_id=job.job_id, event_type="validation_waiver", reason=str(reason),
            actor_id=str(actor_id or ""), actor_role=actor_role,
        )
        job.updated_at = self._now()
        self._save_job(job)
        return self._require_job(job.job_id)

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
        warnings: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
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
            warnings=list(warnings or []),
            metadata=dict(metadata or {}),
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

    def append_event(
        self,
        *,
        job_id: str,
        event_type: DevJobEventType,
        summary: str = "",
        reason: str | None = None,
        actor_id: str = "",
        actor_role: AgentRole | None = None,
        warnings: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append an audit event to a DevJob without changing its lifecycle state.

        Used to surface blocked, failed, or degraded execution conditions through
        an existing, append-only DevJob surface. This never mutates authority or
        advances the DevJob; it only records.
        """
        self._require_job(job_id)
        event = DevJobEvent(
            job_id=job_id,
            event_type=event_type,
            summary=str(summary or ""),
            reason=reason,
            actor_id=str(actor_id or ""),
            actor_role=actor_role.value if actor_role is not None else None,
            warnings=list(warnings or []),
            metadata=dict(metadata or {}),
        )
        self._save_event(job_id, event)
        return event.to_dict()

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        events_dir = self._job_dir(job_id) / "events"
        if not events_dir.exists():
            return []
        events = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(events_dir.glob("*.json"))]
        return sorted(events, key=lambda item: item.get("recorded_at", ""))

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

    def _validate_completion_requirements(self, job: DevJob) -> None:
        """Enforces the completion gate: validation attached (or a governed
        waiver) and a git synchronization reference recorded. Reviewed-status is
        already enforced by ALLOWED_TRANSITIONS. Governed events are read from
        the append-only event store (Sprint 21.1/21.5 event API)."""
        results = self.list_results(job.job_id)
        events = self.list_events(job.job_id)
        has_validation = any(result.get("validation_run_id") for result in results)
        has_waiver = any(event.get("event_type") == "validation_waiver" for event in events)
        if not (has_validation or has_waiver):
            raise ValueError("devjob_completion_requires_validation_or_waiver")
        has_git_sync = any(
            result.get("branch_name") or result.get("public_branch_or_pr") for result in results
        ) or any(event.get("event_type") == "git_sync_attached" for event in events)
        if not has_git_sync:
            raise ValueError("devjob_completion_requires_git_sync_reference")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

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

    def _save_event(self, job_id: str, event: DevJobEvent) -> None:
        events_dir = self._job_dir(job_id) / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        # Prefix with the timestamp so directory ordering matches append order.
        path = events_dir / f"{event.recorded_at.replace(':', '').replace('.', '')}_{event.event_id}.json"
        path.write_text(event.model_dump_json(indent=2), encoding="utf-8")

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
