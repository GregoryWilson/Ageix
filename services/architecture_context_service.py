from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.architecture import (
    ArchitectureContext,
    ArchitectureDescription,
    ArchitectureDescriptionState,
    ArchitectureNode,
)
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService


class ArchitectureContextService:
    """Build summary-first architecture context packets without repository-wide discovery."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = ArchitectureRegistryService(self.repo_root)
        self.guidance_service = ArchitectureGuidanceService(self.repo_root)
        self.guidance_context_service = ArchitectureGuidanceContextService(self.repo_root)
        self.root = self.repo_root / ".ageix" / "architecture"
        self.descriptions_root = self.root / "descriptions"
        self.description_index_path = self.descriptions_root / "index.json"

    def create_description(
        self,
        architecture_id_or_path: str,
        *,
        purpose: str = "",
        responsibilities: list[str] | None = None,
        boundaries: list[str] | None = None,
        open_questions: list[str] | None = None,
        detailed_description: str = "",
        source_actor: str = "architect_worker",
        state: str | ArchitectureDescriptionState = ArchitectureDescriptionState.DRAFT,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureDescription:
        node = self.registry.require_node(architecture_id_or_path)
        version = self._next_version(node.architecture_id)
        description = ArchitectureDescription(
            architecture_id=node.architecture_id,
            project_id=node.project_id,
            version=version,
            state=state if isinstance(state, ArchitectureDescriptionState) else ArchitectureDescriptionState(str(state)),
            source_actor=str(source_actor or "architect_worker"),
            purpose=str(purpose or node.description or ""),
            responsibilities=self._clean_list(responsibilities),
            boundaries=self._clean_list(boundaries),
            open_questions=self._clean_list(open_questions),
            detailed_description=str(detailed_description or ""),
            metadata=dict(metadata or {}),
        )
        return self._persist_description(description)

    def create_draft_from_node(self, architecture_id_or_path: str, *, source_actor: str = "architect_worker") -> ArchitectureDescription:
        node = self.registry.require_node(architecture_id_or_path)
        children = self.registry.get_children(node.architecture_id)["children"]
        responsibilities = [f"Owns the {child['name']} child component." for child in children]
        if not responsibilities:
            responsibilities = [f"Represents the {node.name} {node.node_type.value} within {node.project_id}."]
        boundaries = ["Does not own evidence package contents; it links to evidence through governed package identifiers."]
        open_questions = [] if node.description.strip() else ["Purpose and responsibilities need architect review."]
        return self.create_description(
            node.architecture_id,
            purpose=node.description,
            responsibilities=responsibilities,
            boundaries=boundaries,
            open_questions=open_questions,
            detailed_description=node.description,
            source_actor=source_actor,
            state=ArchitectureDescriptionState.DRAFT,
            metadata={"generated_from_node": True},
        )

    def mark_description_reviewed(self, description_id: str, *, reviewed_by: str = "chair") -> ArchitectureDescription:
        description = self.require_description(description_id)
        description.state = ArchitectureDescriptionState.REVIEWED
        description.reviewed_by = str(reviewed_by or "chair")
        description.updated_at = datetime.now(timezone.utc).isoformat()
        return self._persist_description(description)

    def approve_description(self, description_id: str, *, approved_by: str = "chair") -> ArchitectureDescription:
        description = self.require_description(description_id)
        description.state = ArchitectureDescriptionState.APPROVED
        description.reviewed_by = description.reviewed_by or str(approved_by or "chair")
        description.approved_by = str(approved_by or "chair")
        description.updated_at = datetime.now(timezone.utc).isoformat()
        persisted = self._persist_description(description)
        node = self.registry.require_node(description.architecture_id)
        node.description_state = ArchitectureDescriptionState.APPROVED
        self.registry.upsert_node(node)
        return persisted

    def list_descriptions(self, architecture_id_or_path: str | None = None) -> dict[str, Any]:
        entries = list(self._load_description_index().get("descriptions", []))
        if architecture_id_or_path:
            node = self.registry.require_node(architecture_id_or_path)
            entries = [entry for entry in entries if entry.get("architecture_id") == node.architecture_id]
        entries.sort(key=lambda item: (str(item.get("architecture_id") or ""), int(item.get("version") or 0)))
        return {"descriptions": entries, "count": len(entries)}

    def get_description(self, description_id: str) -> ArchitectureDescription | None:
        path = self._description_path(description_id)
        if not path.exists():
            return None
        return ArchitectureDescription(**json.loads(path.read_text(encoding="utf-8")))

    def require_description(self, description_id: str) -> ArchitectureDescription:
        description = self.get_description(description_id)
        if description is None:
            raise ValueError("architecture_description_not_found")
        return description

    def active_description_for_node(self, architecture_id_or_path: str) -> ArchitectureDescription | None:
        node = self.registry.require_node(architecture_id_or_path)
        descriptions = [
            self.require_description(str(entry["description_id"]))
            for entry in self._load_description_index().get("descriptions", [])
            if entry.get("architecture_id") == node.architecture_id
        ]
        if not descriptions:
            return None
        rank = {
            ArchitectureDescriptionState.APPROVED: 3,
            ArchitectureDescriptionState.REVIEWED: 2,
            ArchitectureDescriptionState.DRAFT: 1,
        }
        descriptions.sort(key=lambda item: (rank.get(item.state, 0), item.version, item.updated_at), reverse=True)
        return descriptions[0]

    def build_context(
        self,
        architecture_id_or_path: str,
        *,
        include_detail: bool = False,
        requester_identity: dict[str, Any] | None = None,
    ) -> ArchitectureContext:
        node = self.registry.require_node(architecture_id_or_path)
        description = self.active_description_for_node(node.architecture_id)
        purpose = (description.purpose if description else "") or node.description
        parent_context = self._parent_context(node)
        child_context = self._child_context(node)
        evidence_summary = self._evidence_summary(node.linked_evidence_package_ids, requester_identity or {"project_id": node.project_id})
        decision_summary = self._decision_summary(node.linked_decision_trace_ids, requester_identity or {"project_id": node.project_id})
        guidance = self.guidance_service.get_guidance(project_id=node.project_id, architecture_id=node.architecture_id)
        active_principles = guidance.get("principles", [])
        active_intents = guidance.get("intents", [])
        try:
            guidance_context = self.guidance_context_service.build_context_package(architecture_id=node.architecture_id, persist=False)
            guidance_summary = {
                "brief_summary": guidance_context.brief_summary,
                "governing_principles_count": len(guidance_context.governing_principles),
                "active_intent_count": len(guidance_context.active_intent),
                "related_adrs": [item.get("adr_id") for item in guidance_context.decision_context],
                "constraints": guidance_context.constraints,
                "future_direction": guidance_context.future_direction,
                "open_considerations": guidance_context.open_considerations,
                "detail_available": True,
                "detail_path": guidance_context.detail_path,
            }
        except Exception:
            guidance_summary = {"brief_summary": "Guidance context unavailable for this node.", "detail_available": False}
        summary = self._compile_summary(node, purpose, evidence_summary, decision_summary, child_context, active_principles, active_intents)
        context = ArchitectureContext(
            architecture_id=node.architecture_id,
            project_id=node.project_id,
            path=node.path,
            node_type=node.node_type,
            name=node.name,
            summary=summary,
            purpose=purpose,
            responsibilities=list(description.responsibilities if description else []),
            boundaries=list(description.boundaries if description else []),
            open_questions=list(description.open_questions if description else []),
            parent_context=parent_context,
            child_context=child_context,
            linked_evidence_summary=evidence_summary,
            linked_decision_summary=decision_summary,
            active_principles=active_principles,
            active_intents=active_intents,
            guidance={**guidance, "guidance_summary": guidance_summary},
            description=self._description_summary(description) if description else None,
            detail_available=bool(description and (description.detailed_description or description.metadata)),
            context_policy={
                "summary_first": True,
                "architecture_is_interpretive": True,
                "evidence_is_linked_not_absorbed": True,
                "repository_wide_discovery_performed": False,
                "detail_request_supported": True,
                "active_guidance_included": True,
            },
        )
        if include_detail:
            context.detail = {
                "node": node.model_dump(mode="json"),
                "description": description.model_dump(mode="json") if description else None,
                "evidence_link_policy": "Architecture links to evidence package summaries and never owns evidence contents.",
                "decision_link_policy": "Architecture links to decision trace summaries and never rewrites decision history.",
                "guidance_policy": "Architecture context includes lightweight guidance summary; use architecture.guidance.context for full package detail.",
            }
        return context

    def build_subtree_context(self, architecture_id_or_path: str, *, include_detail: bool = False) -> dict[str, Any]:
        subtree = self.registry.get_subtree(architecture_id_or_path)

        def flatten(branch: dict[str, Any]) -> list[dict[str, Any]]:
            node = branch.get("node") or {}
            current = self.build_context(str(node.get("architecture_id")), include_detail=include_detail).model_dump(mode="json")
            rows = [current]
            for child in branch.get("children") or []:
                rows.extend(flatten(child))
            return rows

        return {
            "root_id": subtree["root_id"],
            "contexts": flatten(subtree["subtree"]),
            "context_policy": {"summary_first": True, "repository_wide_discovery_performed": False},
        }

    def _persist_description(self, description: ArchitectureDescription) -> ArchitectureDescription:
        self.descriptions_root.mkdir(parents=True, exist_ok=True)
        path = self._description_path(description.description_id)
        path.write_text(json.dumps(description.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        self._rebuild_description_index()
        return description

    def _description_summary(self, description: ArchitectureDescription | None) -> dict[str, Any] | None:
        if description is None:
            return None
        return {
            "description_id": description.description_id,
            "version": description.version,
            "state": description.state.value,
            "source_actor": description.source_actor,
            "reviewed_by": description.reviewed_by,
            "approved_by": description.approved_by,
            "updated_at": description.updated_at,
        }

    def _parent_context(self, node: ArchitectureNode) -> dict[str, Any] | None:
        if not node.parent_id:
            return None
        parent = self.registry.require_node(node.parent_id)
        return {"architecture_id": parent.architecture_id, "name": parent.name, "path": parent.path, "node_type": parent.node_type.value, "description": parent.description}

    def _child_context(self, node: ArchitectureNode) -> list[dict[str, Any]]:
        children = self.registry.get_children(node.architecture_id)["children"]
        return [
            {
                "architecture_id": child.get("architecture_id"),
                "name": child.get("name"),
                "path": child.get("path"),
                "node_type": child.get("node_type"),
                "linked_evidence_count": child.get("linked_evidence_count", 0),
                "linked_decision_count": child.get("linked_decision_count", 0),
                "description_state": child.get("description_state"),
            }
            for child in children
        ]

    def _evidence_summary(self, package_ids: list[str], requester: dict[str, Any]) -> list[dict[str, Any]]:
        index_path = self.repo_root / ".ageix" / "evidence_packages" / "index.json"
        if not index_path.exists():
            return []
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8")).get("packages", [])
        except Exception:
            return []
        requester_project = str(requester.get("project_id") or "")
        by_id = {str(entry.get("package_id")): entry for entry in entries}
        summaries = []
        for package_id in package_ids:
            entry = by_id.get(str(package_id))
            if not entry:
                summaries.append({"package_id": str(package_id), "visible": False, "reason": "package_summary_not_found"})
                continue
            package_project = str(entry.get("project_id") or "")
            if requester_project and package_project and requester_project != package_project:
                summaries.append({"package_id": str(package_id), "visible": False, "reason": "project_scope_denied"})
                continue
            summaries.append({
                "package_id": str(package_id),
                "visible": True,
                "objective": entry.get("objective"),
                "proposal_id": entry.get("proposal_id"),
                "evidence_plan_id": entry.get("evidence_plan_id"),
                "freshness_status": entry.get("freshness_status"),
                "stale": bool(entry.get("stale", False)),
                "primary_count": int(entry.get("primary_count") or 0),
                "supporting_count": int(entry.get("supporting_count") or 0),
                "validation_count": int(entry.get("validation_count") or 0),
                "governance_status": (entry.get("governance") or {}).get("status"),
            })
        return summaries

    def _decision_summary(self, trace_ids: list[str], requester: dict[str, Any]) -> list[dict[str, Any]]:
        index_path = self.repo_root / ".ageix" / "decision_traces" / "index.json"
        if not index_path.exists():
            return []
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8")).get("traces", [])
        except Exception:
            return []
        requester_project = str(requester.get("project_id") or "")
        by_id = {str(entry.get("trace_id")): entry for entry in entries}
        summaries = []
        for trace_id in trace_ids:
            entry = by_id.get(str(trace_id))
            if not entry:
                summaries.append({"trace_id": str(trace_id), "visible": False, "reason": "decision_trace_summary_not_found"})
                continue
            trace_project = str(entry.get("project_id") or "")
            if requester_project and trace_project and requester_project != trace_project:
                summaries.append({"trace_id": str(trace_id), "visible": False, "reason": "project_scope_denied"})
                continue
            summaries.append({
                "trace_id": str(trace_id),
                "visible": True,
                "decision_id": entry.get("decision_id"),
                "decision_type": entry.get("decision_type"),
                "decision_summary": entry.get("decision_summary"),
                "outcome": entry.get("outcome"),
                "proposal_id": entry.get("proposal_id"),
                "evidence_package_ids": list(entry.get("evidence_package_ids") or []),
                "created_at": entry.get("created_at"),
            })
        return summaries

    def _compile_summary(self, node: ArchitectureNode, purpose: str, evidence: list[dict[str, Any]], decisions: list[dict[str, Any]], children: list[dict[str, Any]], principles: list[dict[str, Any]] | None = None, intents: list[dict[str, Any]] | None = None) -> str:
        purpose_text = purpose.strip() or f"{node.name} is a {node.node_type.value} architecture node."
        return (
            f"{node.path}: {purpose_text} "
            f"Children={len(children)}; linked_evidence={len(evidence)}; linked_decisions={len(decisions)}; "
            f"active_principles={len(principles or [])}; active_intents={len(intents or [])}."
        )

    def _rebuild_description_index(self) -> None:
        entries = []
        for path in sorted(self.descriptions_root.glob("ARCHDESC-*.json")):
            description = ArchitectureDescription(**json.loads(path.read_text(encoding="utf-8")))
            entries.append({
                "description_id": description.description_id,
                "architecture_id": description.architecture_id,
                "project_id": description.project_id,
                "version": description.version,
                "state": description.state.value,
                "source_actor": description.source_actor,
                "reviewed_by": description.reviewed_by,
                "approved_by": description.approved_by,
                "updated_at": description.updated_at,
            })
        entries.sort(key=lambda item: (str(item.get("architecture_id") or ""), int(item.get("version") or 0)))
        self.description_index_path.write_text(json.dumps({"schema_version": 1, "descriptions": entries}, indent=2, sort_keys=True), encoding="utf-8")

    def _load_description_index(self) -> dict[str, Any]:
        if not self.description_index_path.exists():
            return {"schema_version": 1, "descriptions": []}
        return json.loads(self.description_index_path.read_text(encoding="utf-8"))

    def _description_path(self, description_id: str) -> Path:
        return self.descriptions_root / f"{description_id}.json"

    def _next_version(self, architecture_id: str) -> int:
        versions = [
            int(entry.get("version") or 0)
            for entry in self._load_description_index().get("descriptions", [])
            if entry.get("architecture_id") == architecture_id
        ]
        return max(versions or [0]) + 1

    def _clean_list(self, values: list[str] | None) -> list[str]:
        return list(dict.fromkeys(str(item).strip() for item in values or [] if str(item).strip()))
