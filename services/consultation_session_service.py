from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.consultation import ConsultationProposal
from models.consultation_response import ConsultationResponse
from models.evidence_request import EvidenceRequest


class ConsultationSessionService:
    """Creates and persists governed consultation session audit trails."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.consultation_root = self.repo_root / ".ageix" / "manifests" / "consultations"

    def create_session(
        self,
        proposal: ConsultationProposal,
        approval: dict[str, Any] | None = None,
        *,
        consultation_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = consultation_id or self._next_id(proposal)
        session = {
            "consultation_id": session_id,
            "status": "approved" if approval else "proposed",
            "created_at": self._now(),
            "proposal": proposal.model_dump(),
            "approval": approval or {},
            "evidence_dictionary": proposal.evidence_dictionary.model_dump() if proposal.evidence_dictionary else {},
            "evidence_requests": [],
            "evidence_responses": [],
            "consultation_responses": [],
            "turns": [],
            "current_turn": 0,
            "token_usage": {
                "estimated_input_tokens": proposal.token_estimate.estimated_input_tokens,
                "estimated_output_tokens": proposal.token_estimate.estimated_output_tokens,
                "estimated_total_tokens": proposal.token_estimate.estimated_total_tokens,
                "served_evidence_tokens": 0,
            },
            "cost_tracking": proposal.cost_estimate.model_dump() if proposal.cost_estimate else {},
        }
        self._persist_session(session)
        return session

    def load_session(self, consultation_id: str) -> dict[str, Any]:
        path = self._session_path(consultation_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def record_approval(self, consultation_id: str, approval: dict[str, Any]) -> dict[str, Any]:
        session = self.load_session(consultation_id)
        session["approval"] = approval
        session["status"] = "approved"
        session["updated_at"] = self._now()
        self._persist_session(session)
        return session

    def record_evidence_request(self, consultation_id: str, request: EvidenceRequest) -> dict[str, Any]:
        session = self.load_session(consultation_id)
        session.setdefault("evidence_requests", []).append(request.model_dump())
        session["updated_at"] = self._now()
        self._persist_session(session)
        return session

    def record_evidence_response(self, consultation_id: str, response: dict[str, Any]) -> dict[str, Any]:
        session = self.load_session(consultation_id)
        session.setdefault("evidence_responses", []).append(response)
        token_usage = session.setdefault("token_usage", {})
        token_usage["served_evidence_tokens"] = int(token_usage.get("served_evidence_tokens", 0)) + int(response.get("estimated_tokens", 0))
        session["updated_at"] = self._now()
        self._persist_session(session)
        return session

    def record_consultation_response(self, consultation_id: str, response: ConsultationResponse) -> dict[str, Any]:
        session = self.load_session(consultation_id)
        session.setdefault("consultation_responses", []).append(response.model_dump())
        session["updated_at"] = self._now()
        self._persist_session(session)
        return session

    def _persist_session(self, session: dict[str, Any]) -> None:
        session_id = str(session["consultation_id"])
        session_dir = self.consultation_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(session_dir / "session.json", session)
        self._write_json(session_dir / "evidence_requests.json", session.get("evidence_requests", []))
        self._write_json(session_dir / "evidence_responses.json", session.get("evidence_responses", []))
        self._write_json(session_dir / "consultation_responses.json", session.get("consultation_responses", []))

    def _session_path(self, consultation_id: str) -> Path:
        return self.consultation_root / consultation_id / "session.json"

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _next_id(self, proposal: ConsultationProposal) -> str:
        prefix = proposal.consultation_type.value.split("_")[0].upper()[:4]
        year = datetime.now(timezone.utc).year
        existing = sorted(self.consultation_root.glob(f"{prefix}-{year}-*")) if self.consultation_root.exists() else []
        return f"{prefix}-{year}-{len(existing) + 1:03d}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
