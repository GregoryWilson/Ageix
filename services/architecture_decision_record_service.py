from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.architecture_decision_record import ArchitectureDecisionRecord, ArchitectureDecisionRecordStatus
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.decision_trace_service import DecisionTraceService
from services.proposal_service import ProposalService


class ArchitectureDecisionRecordService:
    """Governed Architecture Decision Record lifecycle and immutable accepted ADR retrieval."""

    APPROVED_STATUSES = {ProposalStatus.APPROVED, ProposalStatus.APPROVED_WITH_CONDITIONS}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "architecture" / "adrs"
        self.proposals = ProposalService(self.repo_root)
        self.traces = DecisionTraceService(self.repo_root)

    def propose_adr(
        self,
        *,
        project_id: str,
        session_id: str,
        created_by: str,
        title: str,
        context: str,
        decision: str,
        rationale: str,
        alternatives_considered: list[str] | None = None,
        consequences: list[str] | None = None,
        tradeoffs: list[str] | None = None,
        future_considerations: list[str] | None = None,
        architecture_ids: list[str] | None = None,
        revision_ids: list[str] | None = None,
        related_adr_ids: list[str] | None = None,
        supersedes_adr_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureDecisionRecord:
        clean_title = str(title or "").strip()
        if not clean_title:
            raise ValueError("adr_title_required")
        proposal = self.proposals.create_proposal(Proposal(
            project_id=str(project_id or ""),
            session_id=str(session_id or "architecture-adr"),
            agent_id=str(created_by or "architect_worker"),
            objective=f"Architecture Decision Record: {clean_title}",
            proposal_type=ProposalType.ARCHITECTURE,
            linked_evidence=[str(item) for item in evidence_package_ids or [] if str(item)],
            metadata={
                "source": "architecture_adr_proposal",
                "requires_chair_approval": True,
                "architecture_ids": [str(item) for item in architecture_ids or [] if str(item)],
                "revision_ids": [str(item) for item in revision_ids or [] if str(item)],
                "supersedes_adr_id": supersedes_adr_id,
                "related_adr_ids": [str(item) for item in related_adr_ids or [] if str(item)],
            },
        ))
        adr = ArchitectureDecisionRecord(
            adr_number=self._next_adr_number(),
            project_id=proposal.project_id,
            title=clean_title,
            status=ArchitectureDecisionRecordStatus.PROPOSED,
            context=str(context or ""),
            decision=str(decision or ""),
            rationale=str(rationale or ""),
            alternatives_considered=[str(item) for item in alternatives_considered or [] if str(item)],
            consequences=[str(item) for item in consequences or [] if str(item)],
            tradeoffs=[str(item) for item in tradeoffs or [] if str(item)],
            future_considerations=[str(item) for item in future_considerations or [] if str(item)],
            proposal_id=proposal.proposal_id,
            evidence_package_ids=[str(item) for item in evidence_package_ids or [] if str(item)],
            architecture_ids=[str(item) for item in architecture_ids or [] if str(item)],
            revision_ids=[str(item) for item in revision_ids or [] if str(item)],
            supersedes_adr_id=str(supersedes_adr_id) if supersedes_adr_id else None,
            related_adr_ids=[str(item) for item in related_adr_ids or [] if str(item)],
            created_by=str(created_by or "architect_worker"),
            metadata={
                "proposal_system_reused": True,
                "direct_adr_acceptance": False,
                "mcp_origin_allowed": True,
                **dict(metadata or {}),
            },
        )
        self._persist_new(adr)
        return adr

    def accept_approved_adr(
        self,
        adr_id: str,
        *,
        approved_by: str,
        decision_trace_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureDecisionRecord:
        adr = self._load_adr(adr_id)
        proposal = self.proposals.get_proposal(adr.proposal_id)
        if proposal.status not in self.APPROVED_STATUSES:
            raise PermissionError("approved_adr_proposal_required")
        if adr.status not in {ArchitectureDecisionRecordStatus.DRAFT, ArchitectureDecisionRecordStatus.PROPOSED}:
            raise ValueError("adr_not_acceptance_candidate")
        adr.status = ArchitectureDecisionRecordStatus.ACCEPTED
        adr.approved_by = str(approved_by)
        adr.approved_at = self._now()
        adr.decision_trace_id = decision_trace_id or self._find_decision_trace_id(proposal.proposal_id)
        merged_evidence = list(dict.fromkeys([*adr.evidence_package_ids, *[str(item) for item in evidence_package_ids or [] if str(item)], *proposal.linked_evidence]))
        adr.evidence_package_ids = merged_evidence
        adr.metadata = {
            **dict(adr.metadata or {}),
            "proposal_status": proposal.status.value,
            "governance_reused": True,
            "accepted_adr_immutable": True,
            **dict(metadata or {}),
        }
        self._write(adr)
        if adr.supersedes_adr_id:
            self._supersede_adr(adr.supersedes_adr_id, superseded_by=adr.adr_id)
        return adr

    def list_adrs(
        self,
        *,
        project_id: str | None = None,
        architecture_id: str | None = None,
        revision_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        adrs = self._load_all_adrs()
        if project_id:
            adrs = [item for item in adrs if item.project_id == project_id]
        if architecture_id:
            adrs = [item for item in adrs if architecture_id in item.architecture_ids]
        if revision_id:
            adrs = [item for item in adrs if revision_id in item.revision_ids]
        if status:
            adrs = [item for item in adrs if item.status.value == str(status)]
        adrs.sort(key=lambda item: item.adr_number)
        adrs = adrs[:max(1, int(limit or 50))]
        return {"adrs": [item.model_dump(mode="json") for item in adrs], "count": len(adrs)}

    def get_adr(self, adr_id: str) -> dict[str, Any]:
        return self._load_adr(adr_id).model_dump(mode="json")

    def get_history(self, adr_id: str) -> dict[str, Any]:
        target = self._load_adr(adr_id)
        all_adrs = self._load_all_adrs()
        chain = self._lineage_chain(target, all_adrs)
        return {
            "adr_id": adr_id,
            "adr_number": target.adr_number,
            "project_id": target.project_id,
            "history": [item.model_dump(mode="json") for item in chain],
            "count": len(chain),
            "immutable_history": True,
        }

    def cleanup_adr(self, adr_id: str) -> None:
        path = self.root / str(adr_id)
        if path.exists():
            import shutil
            shutil.rmtree(path)

    def _lineage_chain(self, target: ArchitectureDecisionRecord, all_adrs: list[ArchitectureDecisionRecord]) -> list[ArchitectureDecisionRecord]:
        by_id = {item.adr_id: item for item in all_adrs}
        head = target
        while head.supersedes_adr_id and head.supersedes_adr_id in by_id:
            head = by_id[head.supersedes_adr_id]
        chain = [head]
        current = head
        while True:
            nxt = next((item for item in all_adrs if item.supersedes_adr_id == current.adr_id), None)
            if not nxt:
                break
            chain.append(nxt)
            current = nxt
        return chain

    def _supersede_adr(self, adr_id: str, *, superseded_by: str) -> None:
        adr = self._load_adr(adr_id)
        if adr.status == ArchitectureDecisionRecordStatus.ACCEPTED:
            adr.status = ArchitectureDecisionRecordStatus.SUPERSEDED
            adr.metadata = {**dict(adr.metadata or {}), "superseded_by_adr_id": superseded_by}
            self._write(adr)

    def _next_adr_number(self) -> str:
        max_number = 0
        for adr in self._load_all_adrs():
            try:
                max_number = max(max_number, int(str(adr.adr_number).replace("ADR-", "")))
            except Exception:
                continue
        return f"ADR-{max_number + 1:04d}"

    def _find_decision_trace_id(self, proposal_id: str) -> str | None:
        try:
            traces = self.traces.list_traces(proposal_id=proposal_id, limit=1)
            items = traces.get("traces", [])
            if items:
                return str(items[0].get("trace_id") or "") or None
        except Exception:
            return None
        return None

    def _persist_new(self, adr: ArchitectureDecisionRecord) -> None:
        path = self._path(adr.adr_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_adr_is_immutable")
        path.write_text(json.dumps(adr.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _write(self, adr: ArchitectureDecisionRecord) -> None:
        path = self._path(adr.adr_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(adr.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _load_adr(self, adr_id: str) -> ArchitectureDecisionRecord:
        path = self._path(adr_id)
        if not path.exists():
            raise FileNotFoundError("architecture_adr_not_found")
        return ArchitectureDecisionRecord(**json.loads(path.read_text(encoding="utf-8")))

    def _load_all_adrs(self) -> list[ArchitectureDecisionRecord]:
        if not self.root.exists():
            return []
        return [ArchitectureDecisionRecord(**json.loads(path.read_text(encoding="utf-8"))) for path in self.root.glob("*/adr.json")]

    def _path(self, adr_id: str) -> Path:
        return self.root / str(adr_id) / "adr.json"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
