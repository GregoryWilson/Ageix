from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.artifact import ArtifactReference
from models.worker_launch_artifact import LAUNCHER_DENIED_ACTIONS, WorkerLaunchArtifact
from models.worker_launch_request import WorkerLaunchRequest
from services.artifact_registry_service import ArtifactRegistryService
from services.devjob_lifecycle_service import GOVERNANCE_ROLES, is_greg
from services.devjob_registry_service import DevJobRegistryService
from services.launcher_adapters import get_adapter
from services.worker_admission_service import WorkerAdmissionService

# Governance lineage for the Worker Launcher Foundation (Sprint 21.4). These are
# recorded in every launch artifact's traceability so the handoff can be traced
# back to the approving governance chain. Ageix remains the authoritative store.
GOVERNANCE_LINEAGE = {
    "implementation_proposal_id": "PROP-934ADA8E57B8",
    "architecture_proposal_id": "PROP-A37860D5AED3",
    "source_architecture_revision": "ARCHREVPROP-BAD4815B99BF",
    "architecture_id": "ARCH-AGEIX-WORKERPLATFORM",
    "sprint": "21.4",
}


class WorkerLauncherService:
    """Worker Platform service boundary for the governed launch handoff, per
    PROP-934ADA8E57B8 (Sprint 21.4).

    Implements the workflow Admission Ticket -> Launch Profile -> Launch
    Artifact. Given a valid admission ticket and launch profile, it produces a
    governed, non-authoritative WorkerLaunchArtifact through the existing Ageix
    artifact mechanism.

    It deliberately does NOT execute a worker, manage a process, capture output,
    register callbacks, sequence validation, apply patches, complete or change a
    DevJob, or bypass Chair/human authority. Ageix remains the authoritative
    store; the launch artifact never implies downstream work was executed.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "worker_launcher"
        self.artifacts_root = self.root / "artifacts"
        self.index_path = self.artifacts_root / "index.json"
        self._admission = WorkerAdmissionService(self.repo_root)
        self._devjobs = DevJobRegistryService(self.repo_root)
        self._artifacts = ArtifactRegistryService(self.repo_root)

    @staticmethod
    def _is_authorized_governance(actor_id: str | None, actor_role: AgentRole) -> bool:
        """Producing a manual handoff is governance-controlled (Greg or a
        governance role), preserving Chair/human authority. Kept explicit."""
        return is_greg(actor_id) or actor_role in GOVERNANCE_ROLES

    def create_launch_artifact(
        self,
        *,
        admission_ticket_id: str,
        adapter: str,
        worker_profile_id: str | None = None,
        project_id: str = "Ageix",
        requested_by: str = "",
        notes: str = "",
        actor_id: str | None,
        actor_role: AgentRole,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Authority: governance-controlled. Preserve Chair/human boundary.
        if not self._is_authorized_governance(actor_id, actor_role):
            raise ValueError("worker_launcher_requires_governance")

        # Project context must be explicit (default Ageix). No implicit bypass.
        effective_project_id = str(project_id or "Ageix").strip() or "Ageix"

        request = WorkerLaunchRequest(
            project_id=effective_project_id,
            admission_ticket_id=str(admission_ticket_id or ""),
            worker_profile_id=worker_profile_id,
            adapter=str(adapter or ""),
            requested_by=str(requested_by or actor_id or ""),
            notes=str(notes or ""),
            metadata=dict(metadata or {}),
        )
        if not request.admission_ticket_id:
            raise ValueError("worker_launcher_admission_ticket_required")
        if not request.adapter:
            raise ValueError("worker_launcher_adapter_required")

        # Resolve the manual handoff adapter (unknown -> explicit denial).
        adapter_impl = get_adapter(request.adapter)

        # Admission Ticket: must exist and currently be redeemable. We do NOT
        # redeem it — the admitted worker redeems after the manual handoff.
        ticket = self._admission.get_ticket(request.admission_ticket_id)
        if ticket.status == "revoked":
            raise ValueError("worker_launcher_ticket_revoked")
        if ticket.is_redeemed():
            raise ValueError("worker_launcher_ticket_already_redeemed")
        if ticket.is_expired():
            raise ValueError("worker_launcher_ticket_expired")

        # Project context must line up between request and ticket.
        if ticket.project_id != effective_project_id:
            raise ValueError("worker_launcher_project_mismatch")

        # Launch Profile: resolve (from request or the ticket) and validate.
        profile_id = request.worker_profile_id or ticket.worker_profile_id
        profile = self._admission.get_profile(profile_id)
        if request.worker_profile_id and request.worker_profile_id != ticket.worker_profile_id:
            raise ValueError("worker_launcher_profile_ticket_mismatch")

        # Adapter/profile compatibility keeps the handoff surface explicit.
        if adapter_impl.expected_worker_type and profile.worker_type != adapter_impl.expected_worker_type:
            raise ValueError("worker_launcher_profile_adapter_mismatch")

        # Target DevJob must still exist (read-only; no execution, no mutation).
        try:
            self._devjobs.get_job(ticket.target_id)
        except ValueError:
            raise ValueError("worker_launcher_target_devjob_not_found")

        # Adapter assembles non-authoritative handoff instructions.
        handoff = adapter_impl.build_handoff(ticket=ticket, profile=profile, request=request)

        artifact = WorkerLaunchArtifact(
            project_id=effective_project_id,
            request_id=request.request_id,
            admission_ticket_id=ticket.ticket_id,
            worker_profile_id=profile.profile_id,
            adapter=adapter_impl.adapter_key,
            target_type=ticket.target_type,
            target_id=ticket.target_id,
            worker_id=ticket.worker_id,
            permission_mode=ticket.permission_mode,
            required_next_capability=ticket.required_next_capability,
            handoff_instructions=list(handoff.handoff_instructions),
            launch_reference=dict(handoff.launch_reference),
            denied_actions=list(LAUNCHER_DENIED_ACTIONS),
            authority_scope={
                "chair_authority_preserved": True,
                "human_execution_boundary": "Greg",
                "manual_execution": True,
                "execute_available": False,
                "worker_target": profile.worker_type,
                "permission_mode": ticket.permission_mode.value,
                "adapter_notes": list(handoff.adapter_notes),
            },
            traceability={
                **GOVERNANCE_LINEAGE,
                "admission_ticket_id": ticket.ticket_id,
                "worker_profile_id": profile.profile_id,
                "request_id": request.request_id,
                "target": {"type": ticket.target_type, "id": ticket.target_id, "worker_id": ticket.worker_id},
                "authoritative_store": "ageix",
            },
            created_by=str(actor_id or ""),
            metadata=dict(metadata or {}),
        )

        # Persist the launch artifact record, then register it through the
        # existing governed artifact mechanism (immutable registry object).
        record_path = self._write_artifact_record(artifact)
        governed = self._artifacts.register_artifact(
            artifact_category="other",
            artifact_type="worker_launch_handoff",
            created_by=str(actor_id or "worker_launcher_service"),
            project_id=effective_project_id,
            source_id=artifact.launch_artifact_id,
            summary=f"Manual Claude Code launch handoff for {ticket.target_type} {ticket.target_id}.",
            path=record_path,
            references=[
                ArtifactReference(reference_type="worker_admission_ticket", reference_id=ticket.ticket_id, relationship="admits"),
                ArtifactReference(reference_type="worker_launch_profile", reference_id=profile.profile_id, relationship="describes"),
                ArtifactReference(reference_type="devjob", reference_id=ticket.target_id, relationship="targets"),
                ArtifactReference(reference_type="proposal", reference_id=GOVERNANCE_LINEAGE["implementation_proposal_id"], relationship="governed_by"),
                ArtifactReference(reference_type="proposal", reference_id=GOVERNANCE_LINEAGE["architecture_proposal_id"], relationship="governed_by"),
            ],
            metadata={
                "launch_artifact_id": artifact.launch_artifact_id,
                "adapter": artifact.adapter,
                "non_authoritative": True,
                "execution_performed": False,
                "denied_actions": list(LAUNCHER_DENIED_ACTIONS),
            },
        )
        artifact.governed_artifact_id = str(governed.get("artifact_id"))
        # Re-persist with the governed artifact id linked for full traceability.
        self._write_artifact_record(artifact, overwrite=True)
        self._append_index(artifact)
        return artifact.to_metadata()

    def get_launch_artifact(self, launch_artifact_id: str) -> dict[str, Any]:
        return self._require_artifact(launch_artifact_id).to_metadata()

    def list_launch_artifacts(
        self,
        *,
        project_id: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        artifacts = [WorkerLaunchArtifact(**item) for item in self._read_index()]
        if project_id:
            artifacts = [a for a in artifacts if a.project_id == project_id]
        if target_id:
            artifacts = [a for a in artifacts if a.target_id == target_id]
        artifacts = sorted(artifacts, key=lambda a: a.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = artifacts[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} launch artifact(s) returned.",
            "launch_artifacts": [a.to_summary() for a in page],
            "count": len(page),
            "total_count": len(artifacts),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def delete_launch_artifact(self, launch_artifact_id: str) -> None:
        """Remove a launch artifact record. Reserved for smoke/operational cleanup."""
        index = self._read_index()
        remaining = [item for item in index if item.get("launch_artifact_id") != launch_artifact_id]
        if len(remaining) == len(index):
            raise ValueError("worker_launch_artifact_not_found")
        self._write_index(remaining)
        path = self.artifacts_root / f"{launch_artifact_id}.json"
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Internal storage helpers (mirrors admission/patch registry patterns)
    # ------------------------------------------------------------------

    def _write_artifact_record(self, artifact: WorkerLaunchArtifact, *, overwrite: bool = False) -> Path:
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        path = self.artifacts_root / f"{artifact.launch_artifact_id}.json"
        if path.exists() and not overwrite:
            raise ValueError("worker_launch_artifact_id_collision")
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        return path

    def _append_index(self, artifact: WorkerLaunchArtifact) -> None:
        index = self._read_index()
        index = [item for item in index if item.get("launch_artifact_id") != artifact.launch_artifact_id]
        index.append(artifact.model_dump())
        self._write_index(index)

    def _require_artifact(self, launch_artifact_id: str) -> WorkerLaunchArtifact:
        if not str(launch_artifact_id or "").strip():
            raise ValueError("worker_launch_artifact_id_required")
        for item in self._read_index():
            if item.get("launch_artifact_id") == launch_artifact_id:
                return WorkerLaunchArtifact(**item)
        raise ValueError("worker_launch_artifact_not_found")

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_index(self, records: list[dict[str, Any]]) -> None:
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, indent=2, sort_keys=True, default=str)
        tmp_path = self.index_path.with_name(self.index_path.name + ".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.index_path)
