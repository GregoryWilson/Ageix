from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from models.architecture_guidance import ArchitectureGuidanceStatus, ArchitectureIntent, ArchitecturePrinciple
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.decision_trace_service import DecisionTraceService
from services.proposal_service import ProposalService

T = TypeVar("T", ArchitecturePrinciple, ArchitectureIntent)


class ArchitectureGuidanceService:
    """Governed architecture principles, intent, and derived guidance retrieval."""

    APPROVED_STATUSES = {ProposalStatus.APPROVED, ProposalStatus.APPROVED_WITH_CONDITIONS}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "architecture" / "guidance"
        self.principles_root = self.root / "principles"
        self.intents_root = self.root / "intents"
        self.proposals = ProposalService(self.repo_root)
        self.traces = DecisionTraceService(self.repo_root)

    def propose_principle(
        self,
        *,
        project_id: str,
        session_id: str,
        created_by: str,
        title: str,
        statement: str,
        rationale: str = "",
        scope: str = "project",
        architecture_ids: list[str] | None = None,
        adr_ids: list[str] | None = None,
        revision_ids: list[str] | None = None,
        related_principle_ids: list[str] | None = None,
        supersedes_principle_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitecturePrinciple:
        clean_title = str(title or "").strip()
        clean_statement = str(statement or "").strip()
        if not clean_title:
            raise ValueError("architecture_principle_title_required")
        if not clean_statement:
            raise ValueError("architecture_principle_statement_required")
        proposal = self.proposals.create_proposal(Proposal(
            project_id=str(project_id or ""),
            session_id=str(session_id or "architecture-principle"),
            agent_id=str(created_by or "architect_worker"),
            objective=f"Architecture Principle: {clean_title}",
            proposal_type=ProposalType.ARCHITECTURE,
            linked_evidence=self._clean_list(evidence_package_ids),
            metadata={
                "source": "architecture_principle_proposal",
                "requires_chair_approval": True,
                "scope": str(scope or "project"),
                "architecture_ids": self._clean_list(architecture_ids),
                "adr_ids": self._clean_list(adr_ids),
                "revision_ids": self._clean_list(revision_ids),
                "supersedes_principle_id": supersedes_principle_id,
                "related_principle_ids": self._clean_list(related_principle_ids),
            },
        ))
        principle = ArchitecturePrinciple(
            principle_number=self._next_principle_number(),
            project_id=proposal.project_id,
            title=clean_title,
            statement=clean_statement,
            rationale=str(rationale or ""),
            status=ArchitectureGuidanceStatus.PROPOSED,
            scope=str(scope or "project"),
            proposal_id=proposal.proposal_id,
            evidence_package_ids=self._clean_list(evidence_package_ids),
            architecture_ids=self._clean_list(architecture_ids),
            adr_ids=self._clean_list(adr_ids),
            revision_ids=self._clean_list(revision_ids),
            supersedes_principle_id=str(supersedes_principle_id) if supersedes_principle_id else None,
            related_principle_ids=self._clean_list(related_principle_ids),
            created_by=str(created_by or "architect_worker"),
            metadata={
                "proposal_system_reused": True,
                "direct_principle_acceptance": False,
                "mcp_origin_allowed": True,
                **dict(metadata or {}),
            },
        )
        self._persist_new_principle(principle)
        return principle

    def propose_intent(
        self,
        *,
        project_id: str,
        session_id: str,
        created_by: str,
        title: str,
        summary: str,
        details: str = "",
        scope: str = "project",
        future_considerations: list[str] | None = None,
        architecture_ids: list[str] | None = None,
        adr_ids: list[str] | None = None,
        principle_ids: list[str] | None = None,
        revision_ids: list[str] | None = None,
        related_intent_ids: list[str] | None = None,
        supersedes_intent_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureIntent:
        clean_title = str(title or "").strip()
        clean_summary = str(summary or "").strip()
        if not clean_title:
            raise ValueError("architecture_intent_title_required")
        if not clean_summary:
            raise ValueError("architecture_intent_summary_required")
        proposal = self.proposals.create_proposal(Proposal(
            project_id=str(project_id or ""),
            session_id=str(session_id or "architecture-intent"),
            agent_id=str(created_by or "architect_worker"),
            objective=f"Architecture Intent: {clean_title}",
            proposal_type=ProposalType.ARCHITECTURE,
            linked_evidence=self._clean_list(evidence_package_ids),
            metadata={
                "source": "architecture_intent_proposal",
                "requires_chair_approval": True,
                "scope": str(scope or "project"),
                "architecture_ids": self._clean_list(architecture_ids),
                "adr_ids": self._clean_list(adr_ids),
                "principle_ids": self._clean_list(principle_ids),
                "revision_ids": self._clean_list(revision_ids),
                "supersedes_intent_id": supersedes_intent_id,
                "related_intent_ids": self._clean_list(related_intent_ids),
            },
        ))
        intent = ArchitectureIntent(
            intent_number=self._next_intent_number(),
            project_id=proposal.project_id,
            title=clean_title,
            summary=clean_summary,
            details=str(details or ""),
            status=ArchitectureGuidanceStatus.PROPOSED,
            scope=str(scope or "project"),
            future_considerations=self._clean_list(future_considerations),
            proposal_id=proposal.proposal_id,
            evidence_package_ids=self._clean_list(evidence_package_ids),
            architecture_ids=self._clean_list(architecture_ids),
            adr_ids=self._clean_list(adr_ids),
            principle_ids=self._clean_list(principle_ids),
            revision_ids=self._clean_list(revision_ids),
            supersedes_intent_id=str(supersedes_intent_id) if supersedes_intent_id else None,
            related_intent_ids=self._clean_list(related_intent_ids),
            created_by=str(created_by or "architect_worker"),
            metadata={
                "proposal_system_reused": True,
                "direct_intent_acceptance": False,
                "mcp_origin_allowed": True,
                **dict(metadata or {}),
            },
        )
        self._persist_new_intent(intent)
        return intent

    def accept_approved_principle(
        self,
        principle_id: str,
        *,
        approved_by: str,
        decision_trace_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitecturePrinciple:
        principle = self._load_principle(principle_id)
        proposal = self.proposals.get_proposal(principle.proposal_id)
        if proposal.status not in self.APPROVED_STATUSES:
            raise PermissionError("approved_principle_proposal_required")
        if principle.status not in {ArchitectureGuidanceStatus.DRAFT, ArchitectureGuidanceStatus.PROPOSED}:
            raise ValueError("principle_not_acceptance_candidate")
        principle.status = ArchitectureGuidanceStatus.ACCEPTED
        principle.approved_by = str(approved_by)
        principle.approved_at = self._now()
        principle.decision_trace_id = decision_trace_id or self._find_decision_trace_id(proposal.proposal_id)
        principle.evidence_package_ids = list(dict.fromkeys([*principle.evidence_package_ids, *self._clean_list(evidence_package_ids), *proposal.linked_evidence]))
        principle.metadata = {**dict(principle.metadata or {}), "proposal_status": proposal.status.value, "governance_reused": True, "accepted_principle_immutable": True, **dict(metadata or {})}
        self._write_principle(principle)
        if principle.supersedes_principle_id:
            self._supersede_principle(principle.supersedes_principle_id, superseded_by=principle.principle_id)
        return principle

    def accept_approved_intent(
        self,
        intent_id: str,
        *,
        approved_by: str,
        decision_trace_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureIntent:
        intent = self._load_intent(intent_id)
        proposal = self.proposals.get_proposal(intent.proposal_id)
        if proposal.status not in self.APPROVED_STATUSES:
            raise PermissionError("approved_intent_proposal_required")
        if intent.status not in {ArchitectureGuidanceStatus.DRAFT, ArchitectureGuidanceStatus.PROPOSED}:
            raise ValueError("intent_not_acceptance_candidate")
        intent.status = ArchitectureGuidanceStatus.ACCEPTED
        intent.approved_by = str(approved_by)
        intent.approved_at = self._now()
        intent.decision_trace_id = decision_trace_id or self._find_decision_trace_id(proposal.proposal_id)
        intent.evidence_package_ids = list(dict.fromkeys([*intent.evidence_package_ids, *self._clean_list(evidence_package_ids), *proposal.linked_evidence]))
        intent.metadata = {**dict(intent.metadata or {}), "proposal_status": proposal.status.value, "governance_reused": True, "accepted_intent_immutable": True, **dict(metadata or {})}
        self._write_intent(intent)
        if intent.supersedes_intent_id:
            self._supersede_intent(intent.supersedes_intent_id, superseded_by=intent.intent_id)
        return intent

    def list_principles(self, *, project_id: str | None = None, architecture_id: str | None = None, adr_id: str | None = None, revision_id: str | None = None, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        principles = self._filter_principles(project_id=project_id, architecture_id=architecture_id, adr_id=adr_id, revision_id=revision_id, status=status)
        principles.sort(key=lambda item: item.principle_number)
        principles = principles[:max(1, int(limit or 50))]
        return {"principles": [item.model_dump(mode="json") for item in principles], "count": len(principles)}

    def list_intents(self, *, project_id: str | None = None, architecture_id: str | None = None, adr_id: str | None = None, principle_id: str | None = None, revision_id: str | None = None, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        intents = self._filter_intents(project_id=project_id, architecture_id=architecture_id, adr_id=adr_id, principle_id=principle_id, revision_id=revision_id, status=status)
        intents.sort(key=lambda item: item.intent_number)
        intents = intents[:max(1, int(limit or 50))]
        return {"intents": [item.model_dump(mode="json") for item in intents], "count": len(intents)}

    def get_principle(self, principle_id: str) -> dict[str, Any]:
        return self._load_principle(principle_id).model_dump(mode="json")

    def get_intent(self, intent_id: str) -> dict[str, Any]:
        return self._load_intent(intent_id).model_dump(mode="json")

    def get_principle_history(self, principle_id: str) -> dict[str, Any]:
        target = self._load_principle(principle_id)
        chain = self._principle_lineage_chain(target, self._load_all_principles())
        return {"principle_id": principle_id, "principle_number": target.principle_number, "project_id": target.project_id, "history": [item.model_dump(mode="json") for item in chain], "count": len(chain), "immutable_history": True}

    def get_intent_history(self, intent_id: str) -> dict[str, Any]:
        target = self._load_intent(intent_id)
        chain = self._intent_lineage_chain(target, self._load_all_intents())
        return {"intent_id": intent_id, "intent_number": target.intent_number, "project_id": target.project_id, "history": [item.model_dump(mode="json") for item in chain], "count": len(chain), "immutable_history": True}

    def get_guidance(self, *, project_id: str | None = None, architecture_id: str | None = None, adr_id: str | None = None, revision_id: str | None = None) -> dict[str, Any]:
        principles = self._filter_principles(project_id=project_id, architecture_id=architecture_id, adr_id=adr_id, revision_id=revision_id, status=ArchitectureGuidanceStatus.ACCEPTED.value)
        intents = self._filter_intents(project_id=project_id, architecture_id=architecture_id, adr_id=adr_id, revision_id=revision_id, status=ArchitectureGuidanceStatus.ACCEPTED.value)
        principles.sort(key=lambda item: item.principle_number)
        intents.sort(key=lambda item: item.intent_number)
        return {
            "project_id": project_id,
            "architecture_id": architecture_id,
            "adr_id": adr_id,
            "revision_id": revision_id,
            "principles": [item.model_dump(mode="json") for item in principles],
            "intents": [item.model_dump(mode="json") for item in intents],
            "principle_count": len(principles),
            "intent_count": len(intents),
            "derived_guidance": True,
            "stored_guidance_artifact": False,
        }

    def cleanup_principle(self, principle_id: str) -> None:
        path = self.principles_root / str(principle_id)
        if path.exists():
            shutil.rmtree(path)

    def cleanup_intent(self, intent_id: str) -> None:
        path = self.intents_root / str(intent_id)
        if path.exists():
            shutil.rmtree(path)

    def _filter_principles(self, *, project_id: str | None = None, architecture_id: str | None = None, adr_id: str | None = None, revision_id: str | None = None, status: str | None = None) -> list[ArchitecturePrinciple]:
        items = self._load_all_principles()
        if project_id:
            items = [item for item in items if item.project_id == project_id]
        if architecture_id:
            items = [item for item in items if architecture_id in item.architecture_ids]
        if adr_id:
            items = [item for item in items if adr_id in item.adr_ids]
        if revision_id:
            items = [item for item in items if revision_id in item.revision_ids]
        if status:
            items = [item for item in items if item.status.value == str(status)]
        return items

    def _filter_intents(self, *, project_id: str | None = None, architecture_id: str | None = None, adr_id: str | None = None, principle_id: str | None = None, revision_id: str | None = None, status: str | None = None) -> list[ArchitectureIntent]:
        items = self._load_all_intents()
        if project_id:
            items = [item for item in items if item.project_id == project_id]
        if architecture_id:
            items = [item for item in items if architecture_id in item.architecture_ids]
        if adr_id:
            items = [item for item in items if adr_id in item.adr_ids]
        if principle_id:
            items = [item for item in items if principle_id in item.principle_ids]
        if revision_id:
            items = [item for item in items if revision_id in item.revision_ids]
        if status:
            items = [item for item in items if item.status.value == str(status)]
        return items

    def _principle_lineage_chain(self, target: ArchitecturePrinciple, all_items: list[ArchitecturePrinciple]) -> list[ArchitecturePrinciple]:
        by_id = {item.principle_id: item for item in all_items}
        head = target
        while head.supersedes_principle_id and head.supersedes_principle_id in by_id:
            head = by_id[head.supersedes_principle_id]
        chain = [head]
        current = head
        while True:
            nxt = next((item for item in all_items if item.supersedes_principle_id == current.principle_id), None)
            if not nxt:
                break
            chain.append(nxt)
            current = nxt
        return chain

    def _intent_lineage_chain(self, target: ArchitectureIntent, all_items: list[ArchitectureIntent]) -> list[ArchitectureIntent]:
        by_id = {item.intent_id: item for item in all_items}
        head = target
        while head.supersedes_intent_id and head.supersedes_intent_id in by_id:
            head = by_id[head.supersedes_intent_id]
        chain = [head]
        current = head
        while True:
            nxt = next((item for item in all_items if item.supersedes_intent_id == current.intent_id), None)
            if not nxt:
                break
            chain.append(nxt)
            current = nxt
        return chain

    def _supersede_principle(self, principle_id: str, *, superseded_by: str) -> None:
        principle = self._load_principle(principle_id)
        if principle.status == ArchitectureGuidanceStatus.ACCEPTED:
            principle.status = ArchitectureGuidanceStatus.SUPERSEDED
            principle.metadata = {**dict(principle.metadata or {}), "superseded_by_principle_id": superseded_by}
            self._write_principle(principle)

    def _supersede_intent(self, intent_id: str, *, superseded_by: str) -> None:
        intent = self._load_intent(intent_id)
        if intent.status == ArchitectureGuidanceStatus.ACCEPTED:
            intent.status = ArchitectureGuidanceStatus.SUPERSEDED
            intent.metadata = {**dict(intent.metadata or {}), "superseded_by_intent_id": superseded_by}
            self._write_intent(intent)

    def _next_principle_number(self) -> str:
        max_number = 0
        for item in self._load_all_principles():
            try:
                max_number = max(max_number, int(str(item.principle_number).replace("PRIN-", "")))
            except Exception:
                continue
        return f"PRIN-{max_number + 1:04d}"

    def _next_intent_number(self) -> str:
        max_number = 0
        for item in self._load_all_intents():
            try:
                max_number = max(max_number, int(str(item.intent_number).replace("INTENT-", "")))
            except Exception:
                continue
        return f"INTENT-{max_number + 1:04d}"

    def _find_decision_trace_id(self, proposal_id: str) -> str | None:
        try:
            traces = self.traces.list_traces(proposal_id=proposal_id, limit=1)
            items = traces.get("traces", [])
            if items:
                return str(items[0].get("trace_id") or "") or None
        except Exception:
            return None
        return None

    def _persist_new_principle(self, principle: ArchitecturePrinciple) -> None:
        path = self._principle_path(principle.principle_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_principle_is_immutable")
        path.write_text(json.dumps(principle.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _persist_new_intent(self, intent: ArchitectureIntent) -> None:
        path = self._intent_path(intent.intent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_intent_is_immutable")
        path.write_text(json.dumps(intent.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _write_principle(self, principle: ArchitecturePrinciple) -> None:
        path = self._principle_path(principle.principle_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(principle.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _write_intent(self, intent: ArchitectureIntent) -> None:
        path = self._intent_path(intent.intent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(intent.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _load_principle(self, principle_id: str) -> ArchitecturePrinciple:
        path = self._principle_path(principle_id)
        if not path.exists():
            raise FileNotFoundError("architecture_principle_not_found")
        return ArchitecturePrinciple(**json.loads(path.read_text(encoding="utf-8")))

    def _load_intent(self, intent_id: str) -> ArchitectureIntent:
        path = self._intent_path(intent_id)
        if not path.exists():
            raise FileNotFoundError("architecture_intent_not_found")
        return ArchitectureIntent(**json.loads(path.read_text(encoding="utf-8")))

    def _load_all_principles(self) -> list[ArchitecturePrinciple]:
        if not self.principles_root.exists():
            return []
        return [ArchitecturePrinciple(**json.loads(path.read_text(encoding="utf-8"))) for path in self.principles_root.glob("*/principle.json")]

    def _load_all_intents(self) -> list[ArchitectureIntent]:
        if not self.intents_root.exists():
            return []
        return [ArchitectureIntent(**json.loads(path.read_text(encoding="utf-8"))) for path in self.intents_root.glob("*/intent.json")]

    def _principle_path(self, principle_id: str) -> Path:
        return self.principles_root / str(principle_id) / "principle.json"

    def _intent_path(self, intent_id: str) -> Path:
        return self.intents_root / str(intent_id) / "intent.json"

    def _clean_list(self, values: list[str] | None) -> list[str]:
        return list(dict.fromkeys(str(item).strip() for item in values or [] if str(item).strip()))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
