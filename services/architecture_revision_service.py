from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.architecture import ArchitectureNode
from models.architecture_revision import (
    ArchitectureBaseline,
    ArchitectureRevision,
    ArchitectureRevisionStatus,
    ArchitectureRevisionType,
    ArchitectureSnapshot,
)
from models.proposal import ProposalStatus
from services.architecture_registry_service import ArchitectureRegistryService
from services.decision_trace_service import DecisionTraceService
from services.proposal_service import ProposalService


class ArchitectureRevisionService:
    """Governed architecture baseline evolution through immutable revisions and snapshots."""

    APPROVED_STATUSES = {ProposalStatus.APPROVED, ProposalStatus.APPROVED_WITH_CONDITIONS}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "architecture"
        self.revisions_root = self.root / "revisions"
        self.snapshots_root = self.root / "snapshots"
        self.baselines_root = self.root / "baselines"
        self.registry = ArchitectureRegistryService(self.repo_root)
        self.proposals = ProposalService(self.repo_root)
        self.traces = DecisionTraceService(self.repo_root)

    def apply_approved_revision(
        self,
        *,
        revision_proposal_id: str | None = None,
        proposal_id: str | None = None,
        approved_by: str,
        revision_type: str = "update",
        summary: str | None = None,
        decision_trace_id: str | None = None,
        evidence_package_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureRevision:
        revision_proposal = self._load_revision_proposal(revision_proposal_id, proposal_id)
        proposal = self.proposals.get_proposal(str(revision_proposal.get("linked_proposal_id")))
        if proposal.status not in self.APPROVED_STATUSES:
            raise PermissionError("approved_architecture_proposal_required")

        architecture_id = str(revision_proposal.get("architecture_id") or "")
        node = self.registry.require_node(architecture_id)
        previous_baseline = self.get_current_baseline(architecture_id=architecture_id, project_id=node.project_id, required=False)
        supersedes_revision_id = previous_baseline.active_revision_id if previous_baseline else None
        baseline_version = self._next_baseline_version(architecture_id)

        self._apply_allowed_changes(node, dict(revision_proposal.get("proposed_changes") or {}))
        updated_node = self.registry.upsert_node(node)

        snapshot = ArchitectureSnapshot(
            architecture_id=updated_node.architecture_id,
            project_id=updated_node.project_id,
            revision_id="pending",
            baseline_version=baseline_version,
            root=self.registry.get_subtree(updated_node.architecture_id),
            metadata={
                "immutable_snapshot": True,
                "full_architecture_snapshot": True,
                "source_revision_proposal_id": str(revision_proposal.get("revision_id")),
            },
        )
        revision = ArchitectureRevision(
            architecture_id=updated_node.architecture_id,
            project_id=updated_node.project_id,
            proposal_id=proposal.proposal_id,
            revision_type=ArchitectureRevisionType(str(revision_type or "update")),
            summary=summary or proposal.objective,
            created_by=str(revision_proposal.get("submitted_by") or proposal.agent_id),
            approved_by=str(approved_by),
            supersedes_revision_id=supersedes_revision_id,
            snapshot_id=snapshot.snapshot_id,
            baseline_version=baseline_version,
            decision_trace_id=decision_trace_id or self._find_decision_trace_id(proposal.proposal_id),
            evidence_package_ids=[str(item) for item in evidence_package_ids or proposal.linked_evidence if str(item)],
            metadata={
                "source_revision_proposal_id": str(revision_proposal.get("revision_id")),
                "proposal_status": proposal.status.value,
                "governance_reused": True,
                "direct_registry_mutation": False,
                "immutable_history": True,
                **dict(metadata or {}),
            },
        )
        snapshot.revision_id = revision.revision_id
        snapshot.root.setdefault("metadata", {})
        self._persist_snapshot(snapshot)
        if supersedes_revision_id:
            self._supersede_revision(supersedes_revision_id, superseded_by=revision.revision_id)
        self._persist_revision(revision)
        self._write_baseline(ArchitectureBaseline(
            architecture_id=revision.architecture_id,
            project_id=revision.project_id,
            active_revision_id=revision.revision_id,
            active_snapshot_id=revision.snapshot_id,
            active_version=revision.baseline_version,
            metadata={"authoritative": True, "updated_by_revision_id": revision.revision_id},
        ))
        return revision

    def list_revisions(self, *, project_id: str | None = None, architecture_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        revisions = self._load_all_revisions()
        if project_id:
            revisions = [item for item in revisions if item.project_id == project_id]
        if architecture_id:
            revisions = [item for item in revisions if item.architecture_id == architecture_id]
        revisions.sort(key=lambda item: item.created_at, reverse=True)
        revisions = revisions[:max(1, int(limit or 50))]
        return {"revisions": [item.model_dump(mode="json") for item in revisions], "count": len(revisions)}

    def get_revision(self, revision_id: str, *, include_snapshot: bool = False) -> dict[str, Any]:
        revision = self._load_revision(revision_id)
        result = revision.model_dump(mode="json")
        if include_snapshot:
            result["snapshot"] = self._load_snapshot(revision.snapshot_id).model_dump(mode="json")
        return result

    def get_history(self, *, architecture_id: str, project_id: str | None = None) -> dict[str, Any]:
        revisions = self._load_all_revisions()
        revisions = [item for item in revisions if item.architecture_id == architecture_id and (not project_id or item.project_id == project_id)]
        revisions.sort(key=lambda item: item.created_at)
        baseline = self.get_current_baseline(architecture_id=architecture_id, project_id=project_id, required=False)
        return {
            "architecture_id": architecture_id,
            "project_id": project_id or (baseline.project_id if baseline else None),
            "current_baseline": baseline.model_dump(mode="json") if baseline else None,
            "revisions": [item.model_dump(mode="json") for item in revisions],
            "count": len(revisions),
            "immutable_history": True,
        }

    def get_current_baseline(self, *, architecture_id: str, project_id: str | None = None, required: bool = True) -> ArchitectureBaseline | None:
        path = self.baselines_root / str(architecture_id) / "baseline.json"
        if not path.exists():
            if required:
                raise FileNotFoundError("architecture_baseline_not_found")
            return None
        baseline = ArchitectureBaseline(**json.loads(path.read_text(encoding="utf-8")))
        if project_id and baseline.project_id != project_id:
            if required:
                raise FileNotFoundError("architecture_baseline_not_found")
            return None
        return baseline

    def current_baseline_details(self, *, architecture_id: str, project_id: str | None = None, include_snapshot: bool = True) -> dict[str, Any]:
        baseline = self.get_current_baseline(architecture_id=architecture_id, project_id=project_id)
        revision = self._load_revision(baseline.active_revision_id)
        result = {"baseline": baseline.model_dump(mode="json"), "revision": revision.model_dump(mode="json")}
        if include_snapshot:
            result["snapshot"] = self._load_snapshot(baseline.active_snapshot_id).model_dump(mode="json")
        return result

    def _apply_allowed_changes(self, node: ArchitectureNode, changes: dict[str, Any]) -> None:
        self.registry._validate_revision_scope(changes)  # reuse existing policy boundary
        if isinstance(changes.get("description"), str):
            node.description = str(changes["description"])
        if isinstance(changes.get("metadata"), dict):
            node.metadata.update(dict(changes["metadata"]))
        if isinstance(changes.get("review_metadata"), dict):
            review_metadata = dict(node.metadata.get("review_metadata") or {})
            review_metadata.update(dict(changes["review_metadata"]))
            node.metadata["review_metadata"] = review_metadata
        for key, attr in (("evidence_links", "linked_evidence_package_ids"), ("decision_links", "linked_decision_trace_ids")):
            values = changes.get(key) or []
            if isinstance(values, dict):
                values = values.get("add") or values.get("ids") or []
            current = getattr(node, attr)
            for value in values if isinstance(values, list) else []:
                text = str(value)
                if text and text not in current:
                    current.append(text)
        if isinstance(changes.get("relationships"), dict):
            relationships = dict(node.metadata.get("relationships") or {})
            relationships.update(dict(changes["relationships"]))
            node.metadata["relationships"] = relationships
        if isinstance(changes.get("hierarchy_placement"), dict):
            node.metadata["hierarchy_placement_change"] = dict(changes["hierarchy_placement"])

    def _load_revision_proposal(self, revision_proposal_id: str | None, proposal_id: str | None) -> dict[str, Any]:
        candidates = []
        if revision_proposal_id:
            path = self.root / "revision_proposals" / str(revision_proposal_id) / "revision_proposal.json"
            candidates.append(path)
        else:
            candidates.extend(sorted((self.root / "revision_proposals").glob("*/revision_proposal.json")))
        for path in candidates:
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if revision_proposal_id or (proposal_id and payload.get("linked_proposal_id") == proposal_id):
                return payload
        raise FileNotFoundError("architecture_revision_proposal_not_found")

    def _next_baseline_version(self, architecture_id: str) -> str:
        existing = [item for item in self._load_all_revisions() if item.architecture_id == architecture_id]
        return f"v{len(existing) + 1}"

    def _find_decision_trace_id(self, proposal_id: str) -> str | None:
        try:
            traces = self.traces.list_traces(requester_identity={}, proposal_id=proposal_id, limit=1).get("traces", [])
            return str(traces[0].get("trace_id")) if traces else None
        except Exception:
            return None

    def _persist_revision(self, revision: ArchitectureRevision) -> None:
        path = self.revisions_root / revision.revision_id / "revision.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_revision_is_immutable")
        path.write_text(json.dumps(revision.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _persist_snapshot(self, snapshot: ArchitectureSnapshot) -> None:
        path = self.snapshots_root / snapshot.snapshot_id / "snapshot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_snapshot_is_immutable")
        path.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _write_baseline(self, baseline: ArchitectureBaseline) -> None:
        path = self.baselines_root / baseline.architecture_id / "baseline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(baseline.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _supersede_revision(self, revision_id: str, *, superseded_by: str) -> None:
        revision = self._load_revision(revision_id)
        revision.status = ArchitectureRevisionStatus.SUPERSEDED
        revision.metadata = {**dict(revision.metadata or {}), "superseded_by_revision_id": superseded_by}
        path = self.revisions_root / revision.revision_id / "revision.json"
        path.write_text(json.dumps(revision.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _load_revision(self, revision_id: str) -> ArchitectureRevision:
        path = self.revisions_root / str(revision_id) / "revision.json"
        if not path.exists():
            raise FileNotFoundError("architecture_revision_not_found")
        return ArchitectureRevision(**json.loads(path.read_text(encoding="utf-8")))

    def _load_snapshot(self, snapshot_id: str) -> ArchitectureSnapshot:
        path = self.snapshots_root / str(snapshot_id) / "snapshot.json"
        if not path.exists():
            raise FileNotFoundError("architecture_snapshot_not_found")
        return ArchitectureSnapshot(**json.loads(path.read_text(encoding="utf-8")))

    def _load_all_revisions(self) -> list[ArchitectureRevision]:
        if not self.revisions_root.exists():
            return []
        return [ArchitectureRevision(**json.loads(path.read_text(encoding="utf-8"))) for path in self.revisions_root.glob("*/revision.json")]
