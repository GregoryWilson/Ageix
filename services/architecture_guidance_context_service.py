from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from models.architecture_guidance import ArchitectureGuidanceStatus, ArchitectureIntent, ArchitecturePrinciple
from models.architecture_guidance_context import ArchitectureGuidanceContextPackage
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_revision_service import ArchitectureRevisionService


class ArchitectureGuidanceContextService:
    """Builds first-class summary-first architecture guidance context packages."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "architecture" / "guidance_context"
        self.registry = ArchitectureRegistryService(self.repo_root)
        self.guidance = ArchitectureGuidanceService(self.repo_root)
        self.revisions = ArchitectureRevisionService(self.repo_root)
        self.adrs = ArchitectureDecisionRecordService(self.repo_root)

    def build_context_package(
        self,
        *,
        project_id: str | None = None,
        architecture_id: str | None = None,
        path: str | None = None,
        adr_id: str | None = None,
        revision_id: str | None = None,
        principle_id: str | None = None,
        intent_id: str | None = None,
        persist: bool = False,
        created_by: str = "architecture_guidance_context_service",
    ) -> ArchitectureGuidanceContextPackage:
        node = self._resolve_node(
            project_id=project_id,
            architecture_id=architecture_id,
            path=path,
            adr_id=adr_id,
            revision_id=revision_id,
            principle_id=principle_id,
            intent_id=intent_id,
        )
        ancestry = self._ancestry_nearest_first(node.architecture_id)
        scope_ids = [item.architecture_id for item in ancestry]
        principles = self._effective_principles(node.project_id, scope_ids, principle_id=principle_id, adr_id=adr_id, revision_id=revision_id)
        intents = self._effective_intents(node.project_id, scope_ids, intent_id=intent_id, adr_id=adr_id, revision_id=revision_id)
        revision_summary, revision_lineage = self._revision_context(node.architecture_id, revision_id=revision_id)
        decision_context = self._decision_context(node.project_id, scope_ids, principles, intents, adr_id=adr_id, revision_id=revision_id)
        traceability = self._traceability(principles, intents, decision_context, revision_lineage)
        constraints = [self._principle_summary(item, scope_ids) for item in principles]
        future_direction = self._future_direction(intents, decision_context)
        open_considerations = self._open_considerations(node, intents, decision_context)
        conflicts = self._conflicts(principles, intents)
        package = ArchitectureGuidanceContextPackage(
            project_id=node.project_id,
            architecture_id=node.architecture_id,
            architecture_scope={"architecture_id": node.architecture_id, "path": node.path, "node_type": node.node_type.value, "name": node.name},
            affected_nodes=[self._node_summary(item) for item in ancestry],
            scope={
                "project_id": project_id,
                "architecture_id": architecture_id,
                "path": path,
                "adr_id": adr_id,
                "revision_id": revision_id,
                "principle_id": principle_id,
                "intent_id": intent_id,
                "effective_guidance": True,
                "inheritance": "downward_full_stack",
                "ordering": "nearest_scope_first",
            },
            created_by=created_by,
            source_revision_id=(revision_summary or {}).get("revision_id"),
            active_revision_summary=revision_summary,
            revision_lineage=revision_lineage,
            architecture_node_summary=self._node_summary(node),
            brief_summary=self._brief_summary(node, principles, intents, decision_context, conflicts),
            governing_principles=[self._principle_summary(item, scope_ids) for item in principles],
            active_intent=[self._intent_summary(item, scope_ids) for item in intents],
            decision_context=decision_context,
            constraints=constraints,
            future_direction=future_direction,
            open_considerations=open_considerations,
            conflicts=conflicts,
            traceability=traceability,
            governance_lineage={
                "proposal_ids": self._unique([*(p.proposal_id for p in principles), *(i.proposal_id for i in intents), *(d.get("proposal_id") for d in decision_context)]),
                "decision_trace_ids": self._unique([*(p.decision_trace_id for p in principles), *(i.decision_trace_id for i in intents), *(d.get("decision_trace_id") for d in decision_context)]),
                "evidence_package_ids": self._unique([eid for item in [*principles, *intents] for eid in item.evidence_package_ids] + [eid for d in decision_context for eid in d.get("evidence_package_ids", [])]),
            },
            generated_on_demand=not persist,
            persisted_snapshot=bool(persist),
            detail_path={"tool": "architecture.guidance.context", "arguments": {"architecture_id": node.architecture_id, "persist": False}},
            metadata={"deterministic": True, "no_scoring": True, "conflicts_explicit_only": True, "future_18_9_ready": True},
        )
        if persist:
            self._persist(package)
        return package

    def get_package(self, package_id: str) -> dict[str, Any]:
        path = self._path(package_id)
        if not path.exists():
            raise FileNotFoundError("architecture_guidance_context_package_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    def cleanup_package(self, package_id: str) -> None:
        path = self.root / str(package_id)
        if path.exists():
            shutil.rmtree(path)
        self._rebuild_index()

    def _resolve_node(self, *, project_id: str | None, architecture_id: str | None, path: str | None, adr_id: str | None, revision_id: str | None, principle_id: str | None, intent_id: str | None):
        if architecture_id or path:
            return self.registry.require_node(architecture_id or path)
        if revision_id:
            revision = self.revisions.get_revision(revision_id)
            return self.registry.require_node(str(revision.get("architecture_id") or ""))
        if adr_id:
            adr = self.adrs.get_adr(adr_id)
            arch_ids = list(adr.get("architecture_ids") or [])
            if arch_ids:
                return self.registry.require_node(str(arch_ids[0]))
            project_id = project_id or str(adr.get("project_id") or "")
        if principle_id:
            principle = self.guidance._load_principle(principle_id)
            if principle.architecture_ids:
                return self.registry.require_node(principle.architecture_ids[0])
            project_id = project_id or principle.project_id
        if intent_id:
            intent = self.guidance._load_intent(intent_id)
            if intent.architecture_ids:
                return self.registry.require_node(intent.architecture_ids[0])
            project_id = project_id or intent.project_id
        if project_id:
            nodes = self.registry.list_nodes(project_id=project_id).get("nodes", [])
            project_nodes = [item for item in nodes if item.get("node_type") == "project"]
            if project_nodes:
                return self.registry.require_node(str(project_nodes[0].get("architecture_id")))
        raise ValueError("guidance_context_scope_not_resolved")

    def _ancestry_nearest_first(self, architecture_id: str):
        chain = []
        node = self.registry.require_node(architecture_id)
        while node:
            chain.append(node)
            if not node.parent_id:
                break
            node = self.registry.require_node(node.parent_id)
        return chain

    def _effective_principles(self, project_id: str, scope_ids: list[str], *, principle_id: str | None = None, adr_id: str | None = None, revision_id: str | None = None) -> list[ArchitecturePrinciple]:
        items = self.guidance._load_all_principles()
        items = [item for item in items if item.project_id == project_id and item.status == ArchitectureGuidanceStatus.ACCEPTED]
        if principle_id:
            items = [item for item in items if item.principle_id == principle_id]
        elif adr_id:
            items = [item for item in items if adr_id in item.adr_ids]
        elif revision_id:
            items = [item for item in items if revision_id in item.revision_ids]
        else:
            items = [item for item in items if not item.architecture_ids or any(arch_id in scope_ids for arch_id in item.architecture_ids)]
        return self._order_by_scope(items, scope_ids, "architecture_ids", "principle_number")

    def _effective_intents(self, project_id: str, scope_ids: list[str], *, intent_id: str | None = None, adr_id: str | None = None, revision_id: str | None = None) -> list[ArchitectureIntent]:
        items = self.guidance._load_all_intents()
        items = [item for item in items if item.project_id == project_id and item.status == ArchitectureGuidanceStatus.ACCEPTED]
        if intent_id:
            items = [item for item in items if item.intent_id == intent_id]
        elif adr_id:
            items = [item for item in items if adr_id in item.adr_ids]
        elif revision_id:
            items = [item for item in items if revision_id in item.revision_ids]
        else:
            items = [item for item in items if not item.architecture_ids or any(arch_id in scope_ids for arch_id in item.architecture_ids)]
        return self._order_by_scope(items, scope_ids, "architecture_ids", "intent_number")

    def _order_by_scope(self, items: list[Any], scope_ids: list[str], attr: str, number_attr: str) -> list[Any]:
        def rank(item: Any) -> tuple[int, str]:
            ids = list(getattr(item, attr, []) or [])
            if not ids:
                idx = len(scope_ids) + 1
            else:
                idx = min((scope_ids.index(value) for value in ids if value in scope_ids), default=len(scope_ids))
            return (idx, str(getattr(item, number_attr, "")))
        return sorted(items, key=rank)

    def _revision_context(self, architecture_id: str, *, revision_id: str | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        try:
            history = self.revisions.get_history(architecture_id=architecture_id)
        except Exception:
            return None, []
        revisions = list(history.get("revisions") or [])
        active_id = revision_id or ((history.get("current_baseline") or {}).get("active_revision_id"))
        active = next((item for item in revisions if item.get("revision_id") == active_id), None)
        lineage = [{"revision_id": item.get("revision_id"), "summary": item.get("summary"), "status": item.get("status"), "baseline_version": item.get("baseline_version"), "supersedes_revision_id": item.get("supersedes_revision_id"), "decision_trace_id": item.get("decision_trace_id"), "evidence_package_ids": item.get("evidence_package_ids", [])} for item in revisions]
        summary = None
        if active:
            summary = {"revision_id": active.get("revision_id"), "summary": active.get("summary"), "baseline_version": active.get("baseline_version"), "decision_trace_id": active.get("decision_trace_id"), "evidence_package_ids": active.get("evidence_package_ids", [])}
        return summary, lineage

    def _decision_context(self, project_id: str, scope_ids: list[str], principles: list[ArchitecturePrinciple], intents: list[ArchitectureIntent], *, adr_id: str | None = None, revision_id: str | None = None) -> list[dict[str, Any]]:
        try:
            adrs = self.adrs._load_all_adrs()
        except Exception:
            adrs = []
        ids = set()
        for item in principles:
            ids.update(item.adr_ids)
        for item in intents:
            ids.update(item.adr_ids)
        rows = []
        for adr in adrs:
            if adr.project_id != project_id:
                continue
            include = False
            if adr_id and adr.adr_id == adr_id:
                include = True
            elif revision_id and revision_id in adr.revision_ids:
                include = True
            elif adr.adr_id in ids:
                include = True
            elif not adr.architecture_ids or any(arch_id in scope_ids for arch_id in adr.architecture_ids):
                include = True
            if include:
                rows.append({"adr_id": adr.adr_id, "adr_number": adr.adr_number, "title": adr.title, "status": adr.status.value, "decision": adr.decision, "rationale": adr.rationale, "proposal_id": adr.proposal_id, "decision_trace_id": adr.decision_trace_id, "evidence_package_ids": adr.evidence_package_ids, "architecture_ids": adr.architecture_ids, "revision_ids": adr.revision_ids, "future_considerations": adr.future_considerations})
        rows.sort(key=lambda item: str(item.get("adr_number") or ""))
        return rows

    def _principle_summary(self, principle: ArchitecturePrinciple, scope_ids: list[str]) -> dict[str, Any]:
        return {"principle_id": principle.principle_id, "principle_number": principle.principle_number, "title": principle.title, "statement": principle.statement, "rationale": principle.rationale, "scope": principle.scope, "scope_distance": self._scope_distance(principle.architecture_ids, scope_ids), "proposal_id": principle.proposal_id, "decision_trace_id": principle.decision_trace_id, "evidence_package_ids": principle.evidence_package_ids, "adr_ids": principle.adr_ids, "revision_ids": principle.revision_ids, "summary": principle.statement}

    def _intent_summary(self, intent: ArchitectureIntent, scope_ids: list[str]) -> dict[str, Any]:
        return {"intent_id": intent.intent_id, "intent_number": intent.intent_number, "title": intent.title, "summary": intent.summary, "details": intent.details, "scope": intent.scope, "scope_distance": self._scope_distance(intent.architecture_ids, scope_ids), "future_considerations": intent.future_considerations, "proposal_id": intent.proposal_id, "decision_trace_id": intent.decision_trace_id, "evidence_package_ids": intent.evidence_package_ids, "adr_ids": intent.adr_ids, "principle_ids": intent.principle_ids, "revision_ids": intent.revision_ids}

    def _node_summary(self, node: Any) -> dict[str, Any]:
        return {"architecture_id": node.architecture_id, "project_id": node.project_id, "path": node.path, "node_type": node.node_type.value, "name": node.name, "description": node.description, "parent_id": node.parent_id}

    def _brief_summary(self, node: Any, principles: list[ArchitecturePrinciple], intents: list[ArchitectureIntent], decisions: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> str:
        return f"Guidance context for {node.name} ({node.path}): principles={len(principles)}, intents={len(intents)}, adrs={len(decisions)}, conflicts={len(conflicts)}."

    def _future_direction(self, intents: list[ArchitectureIntent], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for intent in intents:
            rows.append({"source_type": "intent", "source_id": intent.intent_id, "summary": intent.summary, "items": list(intent.future_considerations or [])})
        for adr in decisions:
            if adr.get("future_considerations"):
                rows.append({"source_type": "adr", "source_id": adr.get("adr_id"), "summary": adr.get("title"), "items": list(adr.get("future_considerations") or [])})
        return rows

    def _open_considerations(self, node: Any, intents: list[ArchitectureIntent], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for item in list((node.metadata or {}).get("open_considerations") or []):
            rows.append({"source_type": "architecture_node", "source_id": node.architecture_id, "summary": str(item)})
        for intent in intents:
            for item in list((intent.metadata or {}).get("open_considerations") or []):
                rows.append({"source_type": "intent", "source_id": intent.intent_id, "summary": str(item)})
        for adr in decisions:
            for item in list((adr.get("metadata") or {}).get("open_considerations") or []):
                rows.append({"source_type": "adr", "source_id": adr.get("adr_id"), "summary": str(item)})
        return rows

    def _conflicts(self, principles: list[ArchitecturePrinciple], intents: list[ArchitectureIntent]) -> list[dict[str, Any]]:
        active_principle_ids = {item.principle_id for item in principles}
        active_intent_ids = {item.intent_id for item in intents}
        conflicts = []
        for item in principles:
            for target in list((item.metadata or {}).get("conflicts_with_principle_ids") or []):
                if target in active_principle_ids:
                    conflicts.append({"source_type": "principle", "source_id": item.principle_id, "target_type": "principle", "target_id": target, "resolution": "exposed_not_resolved"})
        for item in intents:
            for target in list((item.metadata or {}).get("conflicts_with_intent_ids") or []):
                if target in active_intent_ids:
                    conflicts.append({"source_type": "intent", "source_id": item.intent_id, "target_type": "intent", "target_id": target, "resolution": "exposed_not_resolved"})
        return conflicts

    def _traceability(self, principles: list[ArchitecturePrinciple], intents: list[ArchitectureIntent], decisions: list[dict[str, Any]], revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for item in principles:
            rows.append({"source_type": "principle", "source_id": item.principle_id, "summary": item.title, "principle_id": item.principle_id, "proposal_id": item.proposal_id, "decision_trace_id": item.decision_trace_id, "evidence_package_ids": item.evidence_package_ids, "adr_ids": item.adr_ids, "revision_ids": item.revision_ids})
        for item in intents:
            rows.append({"source_type": "intent", "source_id": item.intent_id, "summary": item.title, "intent_id": item.intent_id, "proposal_id": item.proposal_id, "decision_trace_id": item.decision_trace_id, "evidence_package_ids": item.evidence_package_ids, "adr_ids": item.adr_ids, "principle_ids": item.principle_ids, "revision_ids": item.revision_ids})
        for item in decisions:
            rows.append({"source_type": "adr", "source_id": item.get("adr_id"), "summary": item.get("title"), "adr_id": item.get("adr_id"), "proposal_id": item.get("proposal_id"), "decision_trace_id": item.get("decision_trace_id"), "evidence_package_ids": item.get("evidence_package_ids", []), "revision_ids": item.get("revision_ids", [])})
        for item in revisions:
            rows.append({"source_type": "revision", "source_id": item.get("revision_id"), "summary": item.get("summary"), "revision_id": item.get("revision_id"), "decision_trace_id": item.get("decision_trace_id"), "evidence_package_ids": item.get("evidence_package_ids", [])})
        return rows

    def _scope_distance(self, architecture_ids: list[str], scope_ids: list[str]) -> int | None:
        if not architecture_ids:
            return len(scope_ids) + 1
        candidates = [scope_ids.index(value) for value in architecture_ids if value in scope_ids]
        return min(candidates) if candidates else None

    def _persist(self, package: ArchitectureGuidanceContextPackage) -> None:
        path = self._path(package.package_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_guidance_context_package_is_immutable")
        path.write_text(json.dumps(package.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        packages = []
        for path in self.root.glob("GUIDECTX-*/package.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            packages.append({"package_id": data.get("package_id"), "project_id": data.get("project_id"), "architecture_id": data.get("architecture_id"), "created_at": data.get("created_at"), "brief_summary": data.get("brief_summary")})
        packages.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        (self.root / "index.json").write_text(json.dumps({"packages": packages, "count": len(packages)}, indent=2, sort_keys=True), encoding="utf-8")

    def _path(self, package_id: str) -> Path:
        return self.root / str(package_id) / "package.json"

    @staticmethod
    def _unique(items: list[Any]) -> list[str]:
        return list(dict.fromkeys([str(item) for item in items if item]))
