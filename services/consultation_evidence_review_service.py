from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.proposal_service import ProposalService


class ConsultationEvidenceReviewService:
    """Chair-side review of externally submitted consultation evidence."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "manifests" / "consultations"
        self.proposals = ProposalService(self.repo_root)

    def details(self, consultation_id: str) -> dict[str, Any]:
        path = self.root / consultation_id / "session.json"
        if not path.exists():
            raise FileNotFoundError("consultation_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    def accept(self, consultation_id: str, *, chair_id: str = "chair", reason: str = "") -> dict[str, Any]:
        session = self.details(consultation_id)
        session["status"] = "accepted"
        session["review"] = {
            "reviewed_by": chair_id,
            "decision": "accepted",
            "reason": reason,
            "reviewed_at": self._now(),
            "chair_authoritative": True,
        }
        self._write(consultation_id, session)
        proposal_id = str(session.get("proposal_id") or "")
        consultation_type = str(session.get("consultation_type") or "")
        if proposal_id:
            self.proposals.accept_consultation(proposal_id, consultation_id, consultation_type)
        return session

    def reject(self, consultation_id: str, *, chair_id: str = "chair", reason: str = "") -> dict[str, Any]:
        session = self.details(consultation_id)
        session["status"] = "rejected"
        session["review"] = {
            "reviewed_by": chair_id,
            "decision": "rejected",
            "reason": reason,
            "reviewed_at": self._now(),
            "chair_authoritative": True,
        }
        self._write(consultation_id, session)
        proposal_id = str(session.get("proposal_id") or "")
        if proposal_id:
            self.proposals.reject_consultation(proposal_id, consultation_id)
        return session

    def recommend_rejection(self, consultation_id: str, *, reviewer_id: str, reason: str) -> dict[str, Any]:
        session = self.details(consultation_id)
        recommendations = session.setdefault("review_recommendations", [])
        recommendations.append({
            "reviewer_id": reviewer_id,
            "recommendation": "reject_to_chair",
            "reason": reason,
            "created_at": self._now(),
            "chair_authoritative": False,
        })
        self._write(consultation_id, session)
        return session

    def _write(self, consultation_id: str, session: dict[str, Any]) -> None:
        path = self.root / consultation_id / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(session, indent=2, sort_keys=True), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
