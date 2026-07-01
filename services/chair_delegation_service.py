from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_audit_record import CapabilityAuditRecord
from models.chair_delegation import DEFAULT_DELEGATION_TTL_MINUTES, ChairDelegation
from services.capability_audit_service import CapabilityAuditService
from services.devjob_lifecycle_service import GOVERNANCE_ROLES, is_greg


class ChairDelegationService:
    """Governed registry for temporary Chair delegations, per Sprint 25.4.5.

    A delegation lets the Chair (Greg) explicitly authorize another identity to
    perform a single, narrowly-scoped Chair-only action while no authenticated
    Human Interface exists. This is a temporary bridge:

      - Creation requires explicit Chair approval (Greg or a governance role).
      - Delegations authorize named actions only — never identity impersonation.
      - Delegations expire automatically and are single-use by default.
      - The authorization grant is immutable; only consumption status transitions.
      - Every create and consume is written to the append-only audit trail.

    Ageix remains the authoritative store and all existing governance still
    applies. This service can be removed once the Human Interface is available.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "chair_delegations"
        self.index_path = self.root / "index.json"
        self._audit = CapabilityAuditService(self.repo_root)

    # ------------------------------------------------------------------
    # Creation (explicit Chair approval required)
    # ------------------------------------------------------------------

    def create_delegation(
        self,
        *,
        delegate: str,
        allowed_actions: list[str],
        actor_id: str | None,
        actor_role: AgentRole,
        project_id: str = "Ageix",
        reason: str = "",
        expires_in_minutes: int = DEFAULT_DELEGATION_TTL_MINUTES,
        single_use: bool = True,
        session_id: str = "chair-delegation",
    ) -> ChairDelegation:
        # Explicit Chair approval: only Greg or a governance role may delegate.
        if not (is_greg(actor_id) or actor_role in GOVERNANCE_ROLES):
            raise ValueError("chair_delegation_requires_chair")
        if not str(delegate or "").strip():
            raise ValueError("chair_delegation_delegate_required")
        actions = [str(a).strip() for a in (allowed_actions or []) if str(a).strip()]
        if not actions:
            raise ValueError("chair_delegation_allowed_actions_required")
        # Narrowly scoped: single action preferred for this temporary bridge.
        if len(actions) > 1:
            raise ValueError("chair_delegation_single_action_only")
        try:
            ttl = int(expires_in_minutes)
        except (TypeError, ValueError):
            raise ValueError("chair_delegation_invalid_expiry")
        if ttl <= 0:
            raise ValueError("chair_delegation_invalid_expiry")

        from datetime import timedelta

        now = datetime.now(timezone.utc)
        delegation = ChairDelegation(
            delegator=str(actor_id or ""),
            delegate=str(delegate),
            project_id=str(project_id or "Ageix"),
            allowed_actions=actions,
            reason=str(reason or ""),
            single_use=bool(single_use),
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=ttl)).isoformat(),
        )
        delegation.lifecycle.append(self._event("created", actor_id, actor_role, note="chair_delegation_created"))
        self._save(delegation, append_to_index=True)
        self._record_audit(
            capability_id="chair.delegation.create",
            agent_id=str(actor_id or ""),
            agent_role=actor_role,
            project_id=delegation.project_id,
            session_id=session_id,
            reason="chair_delegation_created",
            delegation=delegation,
        )
        return delegation

    def get_delegation(self, delegation_id: str) -> ChairDelegation:
        return self._require(delegation_id)

    def list_delegations(
        self,
        *,
        delegate: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        items = [ChairDelegation(**item) for item in self._read_index()]
        if delegate:
            items = [d for d in items if d.delegate == delegate]
        if status:
            items = [d for d in items if d.status == status]
        if project_id:
            items = [d for d in items if d.project_id == project_id]
        items = sorted(items, key=lambda d: d.created_at, reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = items[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(page)} chair delegation(s) returned.",
            "delegations": [d.to_summary() for d in page],
            "count": len(page),
            "total_count": len(items),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    # ------------------------------------------------------------------
    # Verification and consumption (governance checks before Chair-only op)
    # ------------------------------------------------------------------

    def verify(
        self,
        delegation_id: str,
        *,
        delegate: str,
        action: str,
        project_id: str | None = None,
        now: datetime | None = None,
    ) -> ChairDelegation:
        """Verify a delegation authorizes `delegate` to perform `action`.

        Read-only: does not consume. Raises ValueError with an explicit reason
        for every failure so nothing is silently allowed.
        """
        delegation = self._require(delegation_id)
        if delegation.status == "revoked":
            raise ValueError("chair_delegation_revoked")
        if delegation.status == "consumed":
            raise ValueError("chair_delegation_already_consumed")
        if delegation.is_expired(now=now):
            raise ValueError("chair_delegation_expired")
        if str(delegate or "") != delegation.delegate:
            raise ValueError("chair_delegation_delegate_mismatch")
        if not delegation.authorizes_action(action):
            raise ValueError("chair_delegation_action_not_authorized")
        if project_id is not None and str(project_id) != delegation.project_id:
            raise ValueError("chair_delegation_project_mismatch")
        return delegation

    def consume(
        self,
        delegation_id: str,
        *,
        delegate: str,
        action: str,
        consumed_for: str | None = None,
        project_id: str | None = None,
        actor_role: AgentRole = AgentRole.UNKNOWN,
        session_id: str = "chair-delegation",
    ) -> ChairDelegation:
        """Atomically re-verify and consume a single-use delegation.

        Records the delegation ID in the append-only audit trail of the
        executed operation (via `consumed_for`).
        """
        delegation = self.verify(delegation_id, delegate=delegate, action=action, project_id=project_id)
        now = datetime.now(timezone.utc)
        # Single-use delegations are spent on consumption. (Non-single-use is
        # out of scope for this bridge but modeled defensively.)
        if delegation.single_use:
            delegation.status = "consumed"
        delegation.consumed_at = now.isoformat()
        delegation.consumed_by = str(delegate)
        delegation.consumed_for = str(consumed_for) if consumed_for else None
        delegation.lifecycle.append(self._event(
            "consumed", delegate, actor_role,
            note=f"chair_delegation_consumed_for:{consumed_for}" if consumed_for else "chair_delegation_consumed",
        ))
        self._save(delegation, append_to_index=False)
        self._record_audit(
            capability_id="chair.delegation.consume",
            agent_id=str(delegate),
            agent_role=actor_role,
            project_id=delegation.project_id,
            session_id=session_id,
            reason=f"chair_delegation_consumed:{action}",
            delegation=delegation,
            consumed_for=consumed_for,
        )
        return delegation

    def delete_delegation(self, delegation_id: str) -> None:
        """Remove a delegation record. Reserved for smoke/operational cleanup."""
        index = self._read_index()
        remaining = [item for item in index if item.get("delegation_id") != delegation_id]
        if len(remaining) == len(index):
            raise ValueError("chair_delegation_not_found")
        self._write_index(remaining)
        path = self.root / f"{delegation_id}.json"
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

    def _record_audit(
        self,
        *,
        capability_id: str,
        agent_id: str,
        agent_role: AgentRole,
        project_id: str,
        session_id: str,
        reason: str,
        delegation: ChairDelegation,
        consumed_for: str | None = None,
    ) -> None:
        self._audit.record(CapabilityAuditRecord(
            session_id=session_id,
            agent_id=agent_id or "unknown",
            capability_id=capability_id,
            success=True,
            reason=reason,
            project_id=project_id,
            agent_role=agent_role.value if isinstance(agent_role, AgentRole) else None,
            metadata={
                "delegation_id": delegation.delegation_id,
                "delegator": delegation.delegator,
                "delegate": delegation.delegate,
                "allowed_actions": list(delegation.allowed_actions),
                "status": delegation.status,
                "consumed_for": consumed_for,
            },
        ))

    def _require(self, delegation_id: str) -> ChairDelegation:
        if not str(delegation_id or "").strip():
            raise ValueError("chair_delegation_id_required")
        for item in self._read_index():
            if item.get("delegation_id") == delegation_id:
                return ChairDelegation(**item)
        raise ValueError("chair_delegation_not_found")

    def _save(self, delegation: ChairDelegation, *, append_to_index: bool) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{delegation.delegation_id}.json").write_text(
            delegation.model_dump_json(indent=2), encoding="utf-8"
        )
        index = self._read_index()
        replaced = False
        for i, item in enumerate(index):
            if item.get("delegation_id") == delegation.delegation_id:
                index[i] = delegation.model_dump()
                replaced = True
                break
        if not replaced:
            if not append_to_index:
                raise ValueError("chair_delegation_not_found")
            index.append(delegation.model_dump())
        self._write_index(index)

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
