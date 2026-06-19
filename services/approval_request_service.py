from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.approval_request import ApprovalRequest, ApprovalStatus


class ApprovalRequestService:
    """Stores human approval requests created by governed proposal flows."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".ageix" / "manifests" / "approval_requests.json"

    def create_request(
        self,
        *,
        proposal_id: str,
        reason: str,
        requested_by: str,
        request_type: str = "other",
        expires_at: str | None = None,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            proposal_id=proposal_id,
            reason=reason,
            requested_by=requested_by,
            request_type=request_type,  # type: ignore[arg-type]
            expires_at=expires_at,
        )
        data = self._load()
        data.setdefault("approval_requests", {})[request.approval_id] = request.model_dump()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        return request

    def get_request(self, approval_id: str) -> ApprovalRequest:
        data = self._load()
        try:
            return ApprovalRequest(**data.get("approval_requests", {})[approval_id])
        except KeyError as exc:
            raise ValueError(f"Unknown approval_id: {approval_id}") from exc

    def update_status(self, approval_id: str, status: ApprovalStatus) -> ApprovalRequest:
        request = self.get_request(approval_id)
        request.status = status
        data = self._load()
        data.setdefault("approval_requests", {})[approval_id] = request.model_dump()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(data)
        return request

    def list_requests(self) -> list[ApprovalRequest]:
        data = self._load()
        return [ApprovalRequest(**raw) for raw in data.get("approval_requests", {}).values()]

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            now = datetime.now(timezone.utc).isoformat()
            return {"schema_version": 1, "created_at": now, "updated_at": now, "approval_requests": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
