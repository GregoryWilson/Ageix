from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.proposal import Proposal, ProposalStatus
from services.current_project_resolution_service import CurrentProjectResolutionService


class ProposalService:
    """Persistent proposal registry for governed external-agent participation."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "manifests" / "proposals"
        self.project_resolution = CurrentProjectResolutionService(self.repo_root)

    def create_proposal(self, proposal: Proposal) -> Proposal:
        now = self._now()
        if not proposal.created_at:
            proposal.created_at = now
        proposal.updated_at = now
        proposal.project_id = self._resolve_project(proposal.project_id, proposal.session_id)
        self._write(proposal)
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal:
        path = self._path(proposal_id)
        if not path.exists():
            raise FileNotFoundError("proposal_not_found")
        return Proposal(**json.loads(path.read_text(encoding="utf-8")))

    def update_status(self, proposal_id: str, status: ProposalStatus | str, **updates: Any) -> Proposal:
        proposal = self.get_proposal(proposal_id)
        proposal.status = ProposalStatus(status)
        for key, value in updates.items():
            if hasattr(proposal, key):
                setattr(proposal, key, value)
        proposal.updated_at = self._now()
        self._write(proposal)
        return proposal

    def link_evidence(self, proposal_id: str, evidence_id: str) -> Proposal:
        proposal = self.get_proposal(proposal_id)
        if evidence_id not in proposal.linked_evidence:
            proposal.linked_evidence.append(evidence_id)
        proposal.updated_at = self._now()
        self._write(proposal)
        return proposal

    def link_consultation(self, proposal_id: str, consultation_id: str, *, accepted: bool | None = None) -> Proposal:
        proposal = self.get_proposal(proposal_id)
        if consultation_id not in proposal.linked_consultations:
            proposal.linked_consultations.append(consultation_id)
        if accepted is True and consultation_id not in proposal.accepted_consultations:
            proposal.accepted_consultations.append(consultation_id)
        if accepted is False and consultation_id not in proposal.rejected_consultations:
            proposal.rejected_consultations.append(consultation_id)
        proposal.updated_at = self._now()
        self._write(proposal)
        return proposal

    def list_proposals(self, project_id: str | None = None, session_id: str | None = None, agent_id: str | None = None) -> list[Proposal]:
        proposals = []
        if self.root.exists():
            for path in sorted(self.root.glob("*/proposal.json"), reverse=True):
                proposal = Proposal(**json.loads(path.read_text(encoding="utf-8")))
                if project_id and proposal.project_id != project_id:
                    continue
                if session_id and proposal.session_id != session_id:
                    continue
                if agent_id and proposal.agent_id != agent_id:
                    continue
                proposals.append(proposal)
        return proposals

    def _write(self, proposal: Proposal) -> None:
        path = self._path(proposal.proposal_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proposal.model_dump(), indent=2, sort_keys=True), encoding="utf-8")

    def _path(self, proposal_id: str) -> Path:
        return self.root / proposal_id / "proposal.json"

    def _resolve_project(self, project_id: str, session_id: str) -> str:
        try:
            return self.project_resolution.resolve_project_id(project_id, session_id)
        except Exception:
            return project_id

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
