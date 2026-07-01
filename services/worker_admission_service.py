from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.permission_mode import PermissionMode
from models.worker_admission_ticket import (
    SUPPORTED_TARGET_TYPES,
    WorkerAdmissionTicket,
)
from models.worker_launch_profile import WorkerLaunchProfile
from services.devjob_lifecycle_service import GOVERNANCE_ROLES, is_greg
from services.devjob_registry_service import DevJobRegistryService


class WorkerAdmissionService:
    """Governed registry for the Worker Admission foundation, per ADR-0014.

    Worker Admission grants participation into a governed DevJob workflow, never
    authority. This service issues, stores, redeems, denies, and revives scoped,
    single-use, time-limited admission tickets for DEVJOB-* targets. Ageix remains
    the authoritative store: a ticket carries no DevJob payload, and redemption
    never bypasses DevJob assignment, worker identity, or governance checks.

    This sprint implements DEVJOB-* targets only. CONV-* and INTERACTION-* are
    future-compatible and are denied as unsupported.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "worker_admission"
        self.profiles_root = self.root / "profiles"
        self.tickets_root = self.root / "tickets"
        self.profiles_index = self.profiles_root / "index.json"
        self.tickets_index = self.tickets_root / "index.json"
        self._devjobs = DevJobRegistryService(self.repo_root)

    # ------------------------------------------------------------------
    # Authorization (governance-controlled, explicit)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_authorized_governance(actor_id: str | None, actor_role: AgentRole) -> bool:
        """Ticket creation and revival are governance-controlled: Greg or a
        governance role only. Kept deliberately simple and explicit."""
        return is_greg(actor_id) or actor_role in GOVERNANCE_ROLES

    # ------------------------------------------------------------------
    # Launch profiles
    # ------------------------------------------------------------------

    def create_profile(
        self,
        *,
        name: str,
        worker_type: str,
        permission_mode: str = PermissionMode.SUPERVISED.value,
        project_id: str = "Ageix",
        description: str = "",
        launch_adapter_hint: str | None = None,
        created_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerLaunchProfile:
        if not str(name or "").strip():
            raise ValueError("worker_admission_profile_name_required")
        if not str(worker_type or "").strip():
            raise ValueError("worker_admission_profile_worker_type_required")
        if not str(created_by or "").strip():
            raise ValueError("worker_admission_profile_created_by_required")
        mode = PermissionMode.parse(permission_mode)

        profile = WorkerLaunchProfile(
            name=str(name),
            worker_type=str(worker_type),
            permission_mode=mode,
            project_id=str(project_id or "Ageix"),
            description=str(description or ""),
            launch_adapter_hint=launch_adapter_hint,
            created_by=str(created_by),
            metadata=dict(metadata or {}),
        )
        self._write_profile(profile)
        index = self._read_index(self.profiles_index)
        index.append(profile.model_dump())
        self._write_index(self.profiles_index, index)
        return profile

    def get_profile(self, profile_id: str) -> WorkerLaunchProfile:
        for item in self._read_index(self.profiles_index):
            if item.get("profile_id") == profile_id:
                return WorkerLaunchProfile(**item)
        raise ValueError("worker_admission_launch_profile_not_found")

    def list_profiles(
        self,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        profiles = [WorkerLaunchProfile(**item) for item in self._read_index(self.profiles_index)]
        if project_id:
            profiles = [p for p in profiles if p.project_id == project_id]
        profiles = sorted(profiles, key=lambda p: p.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = profiles[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} worker launch profile(s) returned.",
            "profiles": [p.to_summary() for p in page],
            "count": len(page),
            "total_count": len(profiles),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    # ------------------------------------------------------------------
    # Admission tickets
    # ------------------------------------------------------------------

    def create_ticket(
        self,
        *,
        target_type: str,
        target_id: str,
        worker_profile_id: str,
        permission_mode: str | None = None,
        required_next_capability: str = "devjob.get",
        project_id: str = "Ageix",
        actor_id: str | None,
        actor_role: AgentRole,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerAdmissionTicket:
        # Authorization: governance-controlled. Arbitrary workers cannot mint.
        if not self._is_authorized_governance(actor_id, actor_role):
            raise ValueError("worker_admission_ticket_create_requires_governance")

        # Target type: DEVJOB-* only this sprint.
        normalized_target_type = str(target_type or "").strip().upper()
        if normalized_target_type not in SUPPORTED_TARGET_TYPES:
            raise ValueError("worker_admission_target_unsupported")
        if not str(target_id or "").strip():
            raise ValueError("worker_admission_target_id_required")
        if not str(target_id).startswith("DEVJOB-"):
            raise ValueError("worker_admission_target_unsupported")

        # Launch profile must exist and be valid.
        profile = self.get_profile(str(worker_profile_id))

        # Permission mode: explicit ticket override or the profile default.
        mode = PermissionMode.parse(permission_mode) if permission_mode is not None else profile.permission_mode

        # Target DevJob must exist, and its assignment resolves the worker
        # identity the ticket is bound to. An unassigned DevJob is ambiguous.
        try:
            job = self._devjobs.get_job(str(target_id))
        except ValueError:
            raise ValueError("worker_admission_target_devjob_not_found")
        if not str(job.assigned_to or "").strip():
            raise ValueError("worker_admission_target_devjob_unassigned")

        ticket = WorkerAdmissionTicket(
            project_id=str(project_id or job.repo_target or "Ageix"),
            target_type=normalized_target_type,
            target_id=str(target_id),
            worker_profile_id=profile.profile_id,
            permission_mode=mode,
            worker_id=str(job.assigned_to),
            required_next_capability=str(required_next_capability or "devjob.get"),
            created_by=str(actor_id or ""),
            metadata=dict(metadata or {}),
        )
        ticket.lifecycle.append(self._event("issued", actor_id, actor_role, note="ticket_created"))
        self._save_ticket(ticket, append_to_index=True)
        return ticket

    def get_ticket(self, ticket_id: str) -> WorkerAdmissionTicket:
        return self._require_ticket(ticket_id)

    def redeem_ticket(
        self,
        *,
        ticket_id: str,
        worker_id: str,
        actor_role: AgentRole,
    ) -> dict[str, Any]:
        ticket = self._require_ticket(ticket_id)

        # A revoked ticket is spent.
        if ticket.status == "revoked":
            raise ValueError("worker_admission_ticket_revoked")
        # Single-use: already redeemed cannot be redeemed again.
        if ticket.is_redeemed():
            raise ValueError("worker_admission_ticket_already_redeemed")
        # Time-limited.
        if ticket.is_expired():
            raise ValueError("worker_admission_ticket_expired")
        # Target still supported.
        if ticket.target_type not in SUPPORTED_TARGET_TYPES:
            raise ValueError("worker_admission_target_unsupported")
        if not str(worker_id or "").strip():
            raise ValueError("worker_admission_redeem_worker_id_required")

        # Redemption must not bypass DevJob assignment or worker identity: the
        # DevJob must still exist and still be assigned to the redeeming worker.
        try:
            job = self._devjobs.get_job(ticket.target_id)
        except ValueError:
            raise ValueError("worker_admission_target_devjob_not_found")
        if str(job.assigned_to or "") != str(worker_id):
            raise ValueError("worker_admission_redeem_worker_not_authorized")
        if str(worker_id) != ticket.worker_id:
            raise ValueError("worker_admission_redeem_worker_not_authorized")

        ticket.status = "redeemed"
        ticket.redeemed_at = datetime.now(timezone.utc).isoformat()
        ticket.redeemed_by = str(worker_id)
        ticket.lifecycle.append(self._event("redeemed", worker_id, actor_role, note="ticket_redeemed"))
        self._save_ticket(ticket, append_to_index=False)
        # Minimal admission context only — never the DevJob payload.
        return ticket.to_admission_context()

    def revive_ticket(
        self,
        *,
        ticket_id: str,
        actor_id: str | None,
        actor_role: AgentRole,
    ) -> WorkerAdmissionTicket:
        """Duplicate a stale ticket into a fresh, traceable one.

        Only an authorized governance actor may revive, and only a stale ticket
        (expired, redeemed, or revoked) may be revived. The new ticket is a fresh
        single-use, time-limited ticket that references its predecessor.
        """
        if not self._is_authorized_governance(actor_id, actor_role):
            raise ValueError("worker_admission_revive_requires_governance")
        source = self._require_ticket(ticket_id)
        if not source.is_stale():
            raise ValueError("worker_admission_ticket_not_stale")

        # Re-validate governed target still exists and remains assigned.
        try:
            job = self._devjobs.get_job(source.target_id)
        except ValueError:
            raise ValueError("worker_admission_target_devjob_not_found")
        if not str(job.assigned_to or "").strip():
            raise ValueError("worker_admission_target_devjob_unassigned")

        revived = WorkerAdmissionTicket(
            project_id=source.project_id,
            target_type=source.target_type,
            target_id=source.target_id,
            worker_profile_id=source.worker_profile_id,
            permission_mode=source.permission_mode,
            worker_id=str(job.assigned_to),
            required_next_capability=source.required_next_capability,
            created_by=str(actor_id or ""),
            revived_from_ticket_id=source.ticket_id,
            metadata={**dict(source.metadata or {}), "revived_from_ticket_id": source.ticket_id},
        )
        revived.lifecycle.append(self._event("issued", actor_id, actor_role, note=f"revived_from:{source.ticket_id}"))
        self._save_ticket(revived, append_to_index=True)
        return revived

    def list_tickets(
        self,
        *,
        target_id: str | None = None,
        worker_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        tickets = [WorkerAdmissionTicket(**item) for item in self._read_index(self.tickets_index)]
        if target_id:
            tickets = [t for t in tickets if t.target_id == target_id]
        if worker_id:
            tickets = [t for t in tickets if t.worker_id == worker_id]
        if status:
            tickets = [t for t in tickets if t.status == status]
        tickets = sorted(tickets, key=lambda t: t.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = tickets[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} admission ticket(s) returned.",
            "tickets": [t.to_summary() for t in page],
            "count": len(page),
            "total_count": len(tickets),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def delete_ticket(self, ticket_id: str) -> None:
        """Remove a ticket record. Reserved for smoke/operational cleanup."""
        index = self._read_index(self.tickets_index)
        remaining = [item for item in index if item.get("ticket_id") != ticket_id]
        if len(remaining) == len(index):
            raise ValueError("worker_admission_ticket_not_found")
        self._write_index(self.tickets_index, remaining)
        path = self.tickets_root / f"{ticket_id}.json"
        if path.exists():
            path.unlink()

    def delete_profile(self, profile_id: str) -> None:
        """Remove a profile record. Reserved for smoke/operational cleanup."""
        index = self._read_index(self.profiles_index)
        remaining = [item for item in index if item.get("profile_id") != profile_id]
        if len(remaining) == len(index):
            raise ValueError("worker_admission_launch_profile_not_found")
        self._write_index(self.profiles_index, remaining)
        path = self.profiles_root / f"{profile_id}.json"
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _event(action: str, actor_id: str | None, actor_role: AgentRole | None, *, note: str = "") -> dict[str, Any]:
        return {
            "action": action,
            "actor_id": actor_id,
            "actor_role": actor_role.value if actor_role is not None else None,
            "note": note,
            "at": datetime.now(timezone.utc).isoformat(),
        }

    def _require_ticket(self, ticket_id: str) -> WorkerAdmissionTicket:
        if not str(ticket_id or "").strip():
            raise ValueError("worker_admission_ticket_id_required")
        for item in self._read_index(self.tickets_index):
            if item.get("ticket_id") == ticket_id:
                return WorkerAdmissionTicket(**item)
        raise ValueError("worker_admission_ticket_not_found")

    def _write_profile(self, profile: WorkerLaunchProfile) -> None:
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        (self.profiles_root / f"{profile.profile_id}.json").write_text(
            profile.model_dump_json(indent=2), encoding="utf-8"
        )

    def _save_ticket(self, ticket: WorkerAdmissionTicket, *, append_to_index: bool) -> None:
        self.tickets_root.mkdir(parents=True, exist_ok=True)
        (self.tickets_root / f"{ticket.ticket_id}.json").write_text(
            ticket.model_dump_json(indent=2), encoding="utf-8"
        )
        index = self._read_index(self.tickets_index)
        replaced = False
        for i, item in enumerate(index):
            if item.get("ticket_id") == ticket.ticket_id:
                index[i] = ticket.model_dump()
                replaced = True
                break
        if not replaced:
            if not append_to_index:
                raise ValueError("worker_admission_ticket_not_found")
            index.append(ticket.model_dump())
        self._write_index(self.tickets_index, index)

    def _read_index(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            return []

    def _write_index(self, path: Path, records: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, indent=2, sort_keys=True, default=str)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, path)
