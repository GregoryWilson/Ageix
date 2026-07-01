from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_audit_record import CapabilityAuditRecord
from models.worker_execution_record import WorkerExecutionRecord
from services.capability_audit_service import CapabilityAuditService
from services.devjob_lifecycle_service import GOVERNANCE_ROLES, is_greg
from services.devjob_registry_service import DevJobRegistryService
from services.launch_providers import LaunchContext, LaunchProvider, resolve_launch_provider
from services.worker_admission_service import WorkerAdmissionService
from services.worker_launcher_service import WorkerLauncherService

CLAUDE_CODE_WORKER_TYPE = "claude_code"
BROWSER_ADAPTER = "claude_code_browser"

# The DevJob status a worker must be in to be launchable by this bridge.
LAUNCHABLE_STATUS = "assigned"


class WorkerExecutionBridgeService:
    """The Worker Execution Bridge, per Sprint 21.5.

    Connects the existing Worker Launcher subsystem to actual worker engagement,
    so a Chair-authorized DevJob no longer terminates at "directive recorded".

    It orchestrates the governed chain — Worker Admission -> Worker Launcher
    Artifact -> Launch Provider -> Worker — reusing the existing admission and
    launcher services. It does NOT know how any worker is launched: that lives
    behind the LaunchProvider abstraction. Governance authorizes engagement; the
    launcher subsystem owns activation. Ageix remains the authoritative store.

    Launch states: worker_launched | worker_queued | worker_launch_failed, each
    recorded on the DevJob lifecycle and in a durable WorkerExecutionRecord.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "worker_launcher" / "executions"
        self.index_path = self.root / "index.json"
        self._devjobs = DevJobRegistryService(self.repo_root)
        self._admission = WorkerAdmissionService(self.repo_root)
        self._launcher = WorkerLauncherService(self.repo_root)
        self._audit = CapabilityAuditService(self.repo_root)

    @staticmethod
    def _is_authorized_governance(actor_id: str | None, actor_role: AgentRole) -> bool:
        """Worker engagement is governance-controlled (Greg or a governance
        role). A directive/delegation authorizes the *directive*, not the launch;
        engagement is a separate governed step, preserving Chair authority."""
        return is_greg(actor_id) or actor_role in GOVERNANCE_ROLES

    # ------------------------------------------------------------------
    # Public: engage a worker for an assigned DevJob
    # ------------------------------------------------------------------

    def engage_worker(
        self,
        *,
        devjob_id: str,
        actor_id: str | None,
        actor_role: AgentRole,
        worker_id: str | None = None,
        worker_profile_id: str | None = None,
        directive_turn_id: str | None = None,
        delegation_id: str | None = None,
        conversation_id: str | None = None,
        project_id: str = "Ageix",
        providers: list[LaunchProvider] | None = None,
    ) -> dict[str, Any]:
        if not self._is_authorized_governance(actor_id, actor_role):
            raise ValueError("worker_execution_requires_governance")

        effective_project_id = str(project_id or "Ageix").strip() or "Ageix"

        # 1. Verify the DevJob exists.
        try:
            job = self._devjobs.get_job(str(devjob_id))
        except ValueError:
            raise ValueError("worker_execution_devjob_not_found")

        # 2. Verify assignment to the requested worker.
        assigned_to = str(job.assigned_to or "").strip()
        if not assigned_to:
            raise ValueError("worker_execution_devjob_unassigned")
        effective_worker_id = str(worker_id or assigned_to)
        if assigned_to != effective_worker_id:
            raise ValueError("worker_execution_worker_mismatch")

        # 3. Verify the DevJob is launchable.
        if job.status != LAUNCHABLE_STATUS:
            raise ValueError(f"worker_execution_devjob_not_launchable:{job.status}")

        # 4/5. Resolve profile, then issue-or-reuse admission ticket and
        #      create-or-reuse the launcher artifact (Worker Admission ->
        #      Worker Launcher Artifact).
        profile = self._resolve_profile(worker_profile_id, actor_id=actor_id, project_id=effective_project_id)
        ticket = self._resolve_ticket(job, profile.profile_id, actor_id=actor_id, actor_role=actor_role,
                                      project_id=effective_project_id)
        artifact = self._resolve_launch_artifact(
            job, ticket, profile.profile_id, actor_id=actor_id, actor_role=actor_role,
            project_id=effective_project_id, directive_turn_id=directive_turn_id,
            delegation_id=delegation_id, conversation_id=conversation_id,
        )

        # 6/7/8. Invoke the launcher abstraction: resolve a launch provider and,
        #        if one is available, launch; otherwise queue.
        context = LaunchContext(
            devjob_id=job.job_id,
            worker_id=effective_worker_id,
            project_id=effective_project_id,
            admission_ticket_id=ticket["ticket_id"],
            launch_artifact_id=artifact["launch_artifact_id"],
            required_next_capability=str(ticket.get("required_next_capability") or "devjob.get"),
            handoff_instructions=list(artifact.get("handoff_instructions") or []),
        )
        provider = resolve_launch_provider(self.repo_root, worker_type=profile.worker_type, providers=providers)

        state, session_ref, reason, provider_key = self._launch_or_queue(provider, context)

        # 9. Transition the DevJob (only after launch or queue).
        status_after = job.status
        if state in ("worker_launched", "worker_queued"):
            updated = self._devjobs.transition_job(
                job.job_id, "in_progress",
                actor_id=effective_worker_id, actor_role=AgentRole.CLAUDE_CODE,
                note=f"worker_execution_bridge:{state}",
            )
            status_after = updated.status

        # 10. Record complete governance + execution traceability.
        record = WorkerExecutionRecord(
            project_id=effective_project_id,
            devjob_id=job.job_id,
            worker_id=effective_worker_id,
            state=state,
            admission_ticket_id=ticket["ticket_id"],
            launch_artifact_id=artifact["launch_artifact_id"],
            directive_turn_id=directive_turn_id,
            delegation_id=delegation_id,
            launch_provider=provider_key,
            worker_session_ref=dict(session_ref or {}),
            devjob_status_after=status_after,
            reason=reason,
            created_by=str(actor_id or ""),
            traceability={
                "devjob_id": job.job_id,
                "worker_id": effective_worker_id,
                "directive_turn_id": directive_turn_id,
                "delegation_id": delegation_id,
                "admission_ticket_id": ticket["ticket_id"],
                "launch_artifact_id": artifact["launch_artifact_id"],
                "governed_artifact_id": artifact.get("governed_artifact_id"),
                "conversation_id": conversation_id,
                "launch_provider": provider_key,
                "authoritative_store": "ageix",
                "sprint": "21.5",
            },
        )
        self._save_record(record)
        self._devjobs.append_event(
            job_id=job.job_id,
            event_type=state,
            summary=f"Worker execution bridge: {state} for {effective_worker_id}.",
            reason=reason,
            actor_id=str(actor_id or ""),
            actor_role=actor_role,
            metadata={
                "execution_id": record.execution_id,
                "admission_ticket_id": ticket["ticket_id"],
                "launch_artifact_id": artifact["launch_artifact_id"],
                "launch_provider": provider_key,
                "worker_session_ref": dict(session_ref or {}),
                "directive_turn_id": directive_turn_id,
                "delegation_id": delegation_id,
                "devjob_status_after": status_after,
            },
        )
        self._record_audit(record, actor_id=actor_id, actor_role=actor_role)
        return record.to_metadata()

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        return self._require_record(execution_id).to_metadata()

    def list_executions(
        self,
        *,
        devjob_id: str | None = None,
        state: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        records = [WorkerExecutionRecord(**item) for item in self._read_index()]
        if devjob_id:
            records = [r for r in records if r.devjob_id == devjob_id]
        if state:
            records = [r for r in records if r.state == state]
        records = sorted(records, key=lambda r: r.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} worker execution record(s) returned.",
            "executions": [r.to_summary() for r in page],
            "count": len(page),
            "total_count": len(records),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    # ------------------------------------------------------------------
    # Internal orchestration helpers
    # ------------------------------------------------------------------

    def _launch_or_queue(self, provider: LaunchProvider | None, context: LaunchContext):
        if provider is None:
            # No launch provider available -> durable queued launch request.
            return ("worker_queued", {}, "no_launch_provider_available", None)
        outcome = provider.launch(context)
        if outcome.launched:
            return ("worker_launched", outcome.session_ref, outcome.detail or "worker_launched", provider.provider_key)
        if outcome.error == "launch_provider_unavailable":
            return ("worker_queued", {}, outcome.detail or "launch_provider_unavailable", provider.provider_key)
        # Provider was available but could not satisfy the request.
        return ("worker_launch_failed", {}, outcome.error or "launch_provider_failed", provider.provider_key)

    def _resolve_profile(self, worker_profile_id: str | None, *, actor_id: str | None, project_id: str):
        if worker_profile_id:
            return self._admission.get_profile(str(worker_profile_id))
        # Reuse an existing claude_code profile if one exists.
        for summary in self._admission.list_profiles(project_id=project_id, limit=100).get("profiles", []):
            if summary.get("worker_type") == CLAUDE_CODE_WORKER_TYPE:
                return self._admission.get_profile(str(summary["profile_id"]))
        # Otherwise create a default claude_code launch profile.
        return self._admission.create_profile(
            name="Claude Code (default)",
            worker_type=CLAUDE_CODE_WORKER_TYPE,
            project_id=project_id,
            description="Default Claude Code launch profile created by the Worker Execution Bridge.",
            launch_adapter_hint=BROWSER_ADAPTER,
            created_by=str(actor_id or "worker_execution_bridge"),
        )

    def _resolve_ticket(self, job, profile_id: str, *, actor_id, actor_role, project_id) -> dict[str, Any]:
        # Reuse an existing, still-usable ticket for this DevJob if present.
        for summary in self._admission.list_tickets(target_id=job.job_id, limit=100).get("tickets", []):
            if summary.get("status") != "issued":
                continue
            ticket = self._admission.get_ticket(str(summary["ticket_id"]))
            if ticket.is_expired() or ticket.is_redeemed():
                continue
            if ticket.worker_id == str(job.assigned_to) and ticket.worker_profile_id == profile_id:
                return ticket.to_metadata()
        # Otherwise issue a fresh admission ticket.
        ticket = self._admission.create_ticket(
            target_type="DEVJOB",
            target_id=job.job_id,
            worker_profile_id=profile_id,
            project_id=project_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        return ticket.to_metadata()

    def _resolve_launch_artifact(self, job, ticket, profile_id, *, actor_id, actor_role, project_id,
                                 directive_turn_id, delegation_id, conversation_id) -> dict[str, Any]:
        # Reuse the most recent launch artifact for this DevJob if present.
        existing = self._launcher.list_launch_artifacts(target_id=job.job_id, limit=1).get("launch_artifacts", [])
        if existing:
            return self._launcher.get_launch_artifact(str(existing[0]["launch_artifact_id"]))
        # Otherwise create it via the existing launcher subsystem.
        return self._launcher.create_launch_artifact(
            admission_ticket_id=ticket["ticket_id"],
            adapter=BROWSER_ADAPTER,
            worker_profile_id=profile_id,
            project_id=project_id,
            requested_by=str(actor_id or ""),
            actor_id=actor_id,
            actor_role=actor_role,
            metadata={
                "directive_turn_id": directive_turn_id,
                "delegation_id": delegation_id,
                "conversation_id": conversation_id,
                "origin": "worker_execution_bridge",
            },
        )

    def _record_audit(self, record: WorkerExecutionRecord, *, actor_id, actor_role) -> None:
        self._audit.record(CapabilityAuditRecord(
            session_id="worker-execution-bridge",
            agent_id=str(actor_id or "unknown"),
            capability_id="worker.launcher.execute",
            success=record.state != "worker_launch_failed",
            reason=f"{record.state}:{record.reason}",
            project_id=record.project_id,
            agent_role=actor_role.value if isinstance(actor_role, AgentRole) else None,
            metadata={
                "execution_id": record.execution_id,
                "devjob_id": record.devjob_id,
                "worker_id": record.worker_id,
                "state": record.state,
                "admission_ticket_id": record.admission_ticket_id,
                "launch_artifact_id": record.launch_artifact_id,
                "directive_turn_id": record.directive_turn_id,
                "delegation_id": record.delegation_id,
                "launch_provider": record.launch_provider,
            },
        ))

    # ------------------------------------------------------------------
    # Durable storage (mirrors admission/launcher registry patterns)
    # ------------------------------------------------------------------

    def _save_record(self, record: WorkerExecutionRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{record.execution_id}.json").write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )
        index = self._read_index()
        index.append(record.model_dump())
        self._write_index(index)

    def _require_record(self, execution_id: str) -> WorkerExecutionRecord:
        if not str(execution_id or "").strip():
            raise ValueError("worker_execution_id_required")
        for item in self._read_index():
            if item.get("execution_id") == execution_id:
                return WorkerExecutionRecord(**item)
        raise ValueError("worker_execution_not_found")

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_index(self, records: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, indent=2, sort_keys=True, default=str)
        tmp_path = self.index_path.with_name(self.index_path.name + ".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.index_path)
