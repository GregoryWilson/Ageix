from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


MUTATING_REPO_CAPABILITIES: frozenset[str] = frozenset({
    "repo.pull",
    "repo.commit",
    "repo.checkout",
    "repo.branch.create",
    "repo.branch.delete",
    "repo.tag.create",
    "repo.tag.delete",
    "repo.push",
    "repo.push.main",
})

# repo.push.main can never be satisfied by a standing sprint grant. It always
# requires a fresh, single-use human approval for that specific call.
NON_GRANTABLE_CAPABILITIES: frozenset[str] = frozenset({"repo.push.main"})


class RepoWriteGovernanceService:
    """Human-controlled authorization gate for mutating git capabilities.

    Two authorization sources exist:
      * Grants: a standing, sprint-scoped human override covering a set of
        mutating capabilities (never repo.push.main).
      * Approvals: a single-use human authorization for one specific
        mutating capability call. Required every time for repo.push.main;
        usable as an alternative to a grant for any other mutating capability.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.governance_root = self.repo_root / ".ageix" / "governance" / "repo_write"
        self.grants_root = self.governance_root / "grants"
        self.approvals_root = self.governance_root / "approvals"

    def create_grant(
        self,
        sprint_id: str,
        granted_by: str = "human",
        capability_ids: list[str] | None = None,
        expires_at: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        if granted_by != "human":
            raise PermissionError("Only a human may grant a sprint-level repo write override.")
        if not sprint_id:
            raise ValueError("sprint_id_required")

        requested = set(capability_ids) if capability_ids else set(MUTATING_REPO_CAPABILITIES)
        non_grantable_requested = requested & NON_GRANTABLE_CAPABILITIES
        if non_grantable_requested:
            raise ValueError(f"capabilities_not_grantable:{','.join(sorted(non_grantable_requested))}")
        unknown = requested - MUTATING_REPO_CAPABILITIES
        if unknown:
            raise ValueError(f"unknown_mutating_capabilities:{','.join(sorted(unknown))}")

        grant_id = f"REPOGRANT-{uuid4().hex[:12].upper()}"
        record = {
            "grant_id": grant_id,
            "sprint_id": sprint_id,
            "capability_ids": sorted(requested),
            "granted_by": granted_by,
            "granted_at": self._now(),
            "reason": reason,
            "expires_at": expires_at,
            "status": "active",
            "revoked_at": None,
            "revoked_by": None,
        }
        self._write(self.grants_root / f"{grant_id}.json", record)
        return record

    def revoke_grant(self, grant_id: str, revoked_by: str = "human") -> dict[str, Any]:
        if revoked_by != "human":
            raise PermissionError("Only a human may revoke a sprint-level repo write override.")
        record = self._read(self.grants_root / f"{grant_id}.json")
        record["status"] = "revoked"
        record["revoked_at"] = self._now()
        record["revoked_by"] = revoked_by
        self._write(self.grants_root / f"{grant_id}.json", record)
        return record

    def list_grants(
        self,
        sprint_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        records = self._list_records(self.grants_root)
        if sprint_id:
            records = [item for item in records if item.get("sprint_id") == sprint_id]
        if status:
            records = [item for item in records if item.get("status") == status]
        records.sort(key=lambda item: str(item.get("granted_at") or ""), reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(records)} repo write grants indexed",
            "grants": page,
            "count": len(page),
            "total_count": len(records),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def create_approval(
        self,
        capability_id: str,
        approved_by: str = "human",
        proposal_id: str | None = None,
        sprint_id: str | None = None,
        target_ref: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        if approved_by != "human":
            raise PermissionError("Only a human may approve a mutating git capability call.")
        if capability_id not in MUTATING_REPO_CAPABILITIES:
            raise ValueError(f"not_a_mutating_capability:{capability_id}")

        approval_id = f"REPOAPPROVAL-{uuid4().hex[:12].upper()}"
        record = {
            "approval_id": approval_id,
            "capability_id": capability_id,
            "proposal_id": proposal_id,
            "sprint_id": sprint_id,
            "target_ref": target_ref,
            "approved_by": approved_by,
            "approved_at": self._now(),
            "reason": reason,
            "status": "active",
            "consumed_at": None,
        }
        self._write(self.approvals_root / f"{approval_id}.json", record)
        return record

    def list_approvals(
        self,
        capability_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        records = self._list_records(self.approvals_root)
        if capability_id:
            records = [item for item in records if item.get("capability_id") == capability_id]
        if status:
            records = [item for item in records if item.get("status") == status]
        records.sort(key=lambda item: str(item.get("approved_at") or ""), reverse=True)
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 100))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "summary": f"{len(records)} repo write approvals indexed",
            "approvals": page,
            "count": len(page),
            "total_count": len(records),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def authorize_mutation(
        self,
        capability_id: str,
        sprint_id: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        if approval_id:
            return self._consume_approval(capability_id, approval_id)

        if capability_id in NON_GRANTABLE_CAPABILITIES:
            return {"allowed": False, "reason": "fresh_human_approval_required", "source": None}

        if sprint_id:
            grant = self._active_grant_for(capability_id, sprint_id)
            if grant:
                return {"allowed": True, "reason": "sprint_grant_active", "source": "grant", "grant_id": grant["grant_id"]}
            return {"allowed": False, "reason": "no_active_sprint_grant_for_capability", "source": None}

        return {"allowed": False, "reason": "approval_or_sprint_grant_required", "source": None}

    def _consume_approval(self, capability_id: str, approval_id: str) -> dict[str, Any]:
        path = self.approvals_root / f"{approval_id}.json"
        if not path.exists():
            return {"allowed": False, "reason": "approval_not_found", "source": None}
        record = self._read(path)
        if record.get("capability_id") != capability_id:
            return {"allowed": False, "reason": "approval_capability_mismatch", "source": None}
        if record.get("status") != "active":
            return {"allowed": False, "reason": "approval_already_consumed_or_revoked", "source": None}
        record["status"] = "consumed"
        record["consumed_at"] = self._now()
        self._write(path, record)
        return {"allowed": True, "reason": "human_approval_consumed", "source": "approval", "approval_id": approval_id}

    def _active_grant_for(self, capability_id: str, sprint_id: str) -> dict[str, Any] | None:
        now = self._now()
        for record in self._list_records(self.grants_root):
            if record.get("status") != "active":
                continue
            if record.get("sprint_id") != sprint_id:
                continue
            if capability_id not in set(record.get("capability_ids") or []):
                continue
            expires_at = record.get("expires_at")
            if expires_at and str(expires_at) <= now:
                continue
            return record
        return None

    def _list_records(self, root: Path) -> list[dict[str, Any]]:
        if not root.exists():
            return []
        records = []
        for path in sorted(root.glob("*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return records

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
