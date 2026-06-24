from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from models.architecture_work_context import ArchitectureWorkContextPackage
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.architecture_revision_service import ArchitectureRevisionService


class ArchitectureWorkContextService:
    """Builds deterministic, summary-first architecture work analysis context packages."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "architecture" / "work_context"
        self.registry = ArchitectureRegistryService(self.repo_root)
        self.guidance_context = ArchitectureGuidanceContextService(self.repo_root)
        self.guidance = ArchitectureGuidanceService(self.repo_root)
        self.adrs = ArchitectureDecisionRecordService(self.repo_root)
        self.revisions = ArchitectureRevisionService(self.repo_root)

    def build_work_context_package(
        self,
        *,
        project_id: str | None = None,
        work_summary: str = "",
        architecture_id: str | None = None,
        architecture_ids: list[str] | None = None,
        path: str | None = None,
        adr_id: str | None = None,
        revision_id: str | None = None,
        principle_id: str | None = None,
        intent_id: str | None = None,
        node_key: str | None = None,
        name: str | None = None,
        persist: bool = False,
        persist_guidance_context: bool = False,
        max_depth: int = 1,
        created_by: str = "architecture_work_context_service",
    ) -> ArchitectureWorkContextPackage:
        if int(max_depth or 1) != 1:
            raise ValueError("architecture_work_context_supports_direct_relationships_only")
        nodes = self._resolve_nodes(
            project_id=project_id,
            architecture_id=architecture_id,
            architecture_ids=architecture_ids,
            path=path,
            adr_id=adr_id,
            revision_id=revision_id,
            principle_id=principle_id,
            intent_id=intent_id,
            node_key=node_key,
            name=name,
        )
        if not nodes:
            raise ValueError("architecture_work_scope_not_resolved")
        effective_project_id = project_id or nodes[0].project_id
        node_ids = [node.architecture_id for node in nodes]
        guidance_packages = [
            self.guidance_context.build_context_package(
                project_id=effective_project_id,
                architecture_id=node.architecture_id,
                persist=bool(persist_guidance_context),
                created_by=created_by,
            )
            for node in nodes
        ]
        relationship_summary, impacted_nodes = self._impact_analysis(nodes)
        package = ArchitectureWorkContextPackage(
            project_id=effective_project_id,
            scope={
                "project_id": project_id,
                "work_summary": work_summary,
                "architecture_id": architecture_id,
                "architecture_ids": architecture_ids or [],
                "path": path,
                "adr_id": adr_id,
                "revision_id": revision_id,
                "principle_id": principle_id,
                "intent_id": intent_id,
                "node_key": node_key,
                "name": name,
                "deterministic_inputs_only": True,
            },
            created_by=created_by,
            work_summary=self._work_summary(work_summary, nodes, impacted_nodes),
            affected_scope={"architecture_ids": node_ids, "count": len(node_ids), "multi_node": len(node_ids) > 1},
            resolved_scope={"resolution_method": self._resolution_method(architecture_id, architecture_ids, path, adr_id, revision_id, principle_id, intent_id, node_key, name), "architecture_ids": node_ids},
            resolved_architecture_nodes=[self._node_summary(node, relationship="resolved_scope") for node in nodes],
            guidance_context=self._guidance_summary(guidance_packages),
            guidance_context_package_ids=[pkg.package_id for pkg in guidance_packages if pkg.persisted_snapshot],
            governing_principles=self._merge_lists([pkg.governing_principles for pkg in guidance_packages], "principle_id"),
            active_intent=self._merge_lists([pkg.active_intent for pkg in guidance_packages], "intent_id"),
            related_adrs=self._merge_lists([pkg.decision_context for pkg in guidance_packages], "adr_id"),
            constraints=self._merge_lists([pkg.constraints for pkg in guidance_packages], "principle_id"),
            future_direction=self._merge_lists([pkg.future_direction for pkg in guidance_packages], "source_id"),
            open_considerations=self._merge_lists([pkg.open_considerations for pkg in guidance_packages], "summary"),
            impacted_nodes=impacted_nodes,
            relationship_summary=relationship_summary,
            revision_context=[{"architecture_id": pkg.architecture_id, "active_revision_summary": pkg.active_revision_summary, "revision_lineage": pkg.revision_lineage} for pkg in guidance_packages],
            governance_lineage=self._governance_lineage(guidance_packages),
            traceability=self._merge_lists([pkg.traceability for pkg in guidance_packages], "source_id"),
            generated_on_demand=not persist,
            persisted_snapshot=bool(persist),
            impact_max_depth=1,
            detail_path={"tool": "architecture.work.context", "arguments": {"architecture_ids": node_ids, "persist": False, "max_depth": 1}},
            metadata={
                "deterministic": True,
                "no_worker_instruction_generation": True,
                "no_task_planning": True,
                "no_scoring": True,
                "impact_analysis": "direct_relationships_only",
                "guidance_context_reused": True,
            },
        )
        if persist:
            self._persist(package)
        return package

    def get_package(self, work_context_id: str) -> dict[str, Any]:
        path = self._path(work_context_id)
        if not path.exists():
            raise FileNotFoundError("architecture_work_context_package_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    def cleanup_package(self, work_context_id: str) -> None:
        path = self.root / str(work_context_id)
        if path.exists():
            shutil.rmtree(path)
        self._rebuild_index()

    def _resolve_nodes(self, *, project_id: str | None, architecture_id: str | None, architecture_ids: list[str] | None, path: str | None, adr_id: str | None, revision_id: str | None, principle_id: str | None, intent_id: str | None, node_key: str | None, name: str | None):
        resolved = []
        for value in [architecture_id, *(architecture_ids or []), path]:
            if value:
                resolved.append(self.registry.require_node(str(value)))
        if adr_id:
            adr = self.adrs.get_adr(adr_id)
            for value in list(adr.get("architecture_ids") or []):
                resolved.append(self.registry.require_node(str(value)))
            project_id = project_id or str(adr.get("project_id") or "")
        if revision_id:
            revision = self.revisions.get_revision(revision_id)
            resolved.append(self.registry.require_node(str(revision.get("architecture_id") or "")))
        if principle_id:
            principle = self.guidance._load_principle(principle_id)
            for value in list(principle.architecture_ids or []):
                resolved.append(self.registry.require_node(str(value)))
            project_id = project_id or principle.project_id
        if intent_id:
            intent = self.guidance._load_intent(intent_id)
            for value in list(intent.architecture_ids or []):
                resolved.append(self.registry.require_node(str(value)))
            project_id = project_id or intent.project_id
        if node_key or name:
            entries = self.registry.list_nodes(project_id=project_id).get("nodes", [])
            if node_key:
                matches = [item for item in entries if item.get("node_key") == node_key]
            else:
                matches = [item for item in entries if item.get("name") == name]
            for item in matches:
                resolved.append(self.registry.require_node(str(item.get("architecture_id"))))
        unique = []
        seen = set()
        for node in resolved:
            if node.architecture_id not in seen:
                unique.append(node)
                seen.add(node.architecture_id)
        return unique

    def _impact_analysis(self, nodes: list[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        resolved_ids = {node.architecture_id for node in nodes}
        impacted: dict[str, dict[str, Any]] = {}
        counts = {"parent": 0, "child": 0, "metadata_relationship": 0}
        for node in nodes:
            if node.parent_id and node.parent_id not in resolved_ids:
                parent = self.registry.get_node(node.parent_id)
                if parent:
                    impacted[parent.architecture_id] = self._node_summary(parent, relationship="parent", source_architecture_id=node.architecture_id)
                    counts["parent"] += 1
            children = self.registry.get_children(node.architecture_id).get("children", [])
            for child in children:
                child_id = str(child.get("architecture_id") or "")
                if child_id and child_id not in resolved_ids:
                    child_node = self.registry.require_node(child_id)
                    impacted[child_id] = self._node_summary(child_node, relationship="child", source_architecture_id=node.architecture_id)
                    counts["child"] += 1
            for rel in self._metadata_relationships(node):
                target_id = str(rel.get("architecture_id") or rel.get("target_architecture_id") or rel.get("target_id") or "")
                if not target_id or target_id in resolved_ids:
                    continue
                target = self.registry.get_node(target_id)
                if target:
                    summary = self._node_summary(target, relationship=str(rel.get("relationship_type") or rel.get("type") or "metadata_relationship"), source_architecture_id=node.architecture_id)
                    summary["relationship_metadata"] = rel
                    impacted[target.architecture_id] = summary
                    counts["metadata_relationship"] += 1
        relationship_summary = {
            "max_depth": 1,
            "traversal": "direct_only",
            "resolved_node_count": len(nodes),
            "impacted_node_count": len(impacted),
            "relationship_counts": counts,
        }
        return relationship_summary, list(impacted.values())

    def _metadata_relationships(self, node: Any) -> list[dict[str, Any]]:
        raw = (node.metadata or {}).get("relationships") or []
        rows: list[dict[str, Any]] = []
        if isinstance(raw, dict):
            for rel_type, targets in raw.items():
                values = targets if isinstance(targets, list) else [targets]
                for target in values:
                    if isinstance(target, dict):
                        row = dict(target)
                        row.setdefault("relationship_type", str(rel_type))
                        rows.append(row)
                    elif target:
                        rows.append({"relationship_type": str(rel_type), "architecture_id": str(target)})
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    rows.append(dict(item))
                elif item:
                    rows.append({"relationship_type": "metadata_relationship", "architecture_id": str(item)})
        return rows

    def _guidance_summary(self, packages: list[Any]) -> dict[str, Any]:
        return {
            "summary_first": True,
            "package_count": len(packages),
            "packages": [
                {
                    "package_id": pkg.package_id,
                    "architecture_id": pkg.architecture_id,
                    "brief_summary": pkg.brief_summary,
                    "persisted_snapshot": pkg.persisted_snapshot,
                    "principle_count": len(pkg.governing_principles),
                    "intent_count": len(pkg.active_intent),
                    "adr_count": len(pkg.decision_context),
                    "detail_path": pkg.detail_path,
                }
                for pkg in packages
            ],
        }

    def _work_summary(self, requested: str, nodes: list[Any], impacted_nodes: list[dict[str, Any]]) -> str:
        prefix = requested.strip() or "Architecture work analysis"
        names = ", ".join(node.name for node in nodes)
        return f"{prefix}: resolved {len(nodes)} architecture node(s) ({names}) with {len(impacted_nodes)} direct impacted node(s)."

    def _node_summary(self, node: Any, *, relationship: str, source_architecture_id: str | None = None) -> dict[str, Any]:
        return {
            "architecture_id": node.architecture_id,
            "project_id": node.project_id,
            "path": node.path,
            "node_key": node.node_key,
            "node_type": node.node_type.value,
            "name": node.name,
            "description": node.description,
            "parent_id": node.parent_id,
            "relationship": relationship,
            "source_architecture_id": source_architecture_id,
        }

    def _resolution_method(self, architecture_id: str | None, architecture_ids: list[str] | None, path: str | None, adr_id: str | None, revision_id: str | None, principle_id: str | None, intent_id: str | None, node_key: str | None, name: str | None) -> str:
        for label, value in [("architecture_id", architecture_id), ("architecture_ids", architecture_ids), ("path", path), ("adr_id", adr_id), ("revision_id", revision_id), ("principle_id", principle_id), ("intent_id", intent_id), ("node_key", node_key), ("name", name)]:
            if value:
                return label
        return "unresolved"

    def _merge_lists(self, groups: list[list[dict[str, Any]]], key: str) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen = set()
        for group in groups:
            for item in group:
                marker = str(item.get(key) or item.get("source_id") or item)
                if marker not in seen:
                    merged.append(item)
                    seen.add(marker)
        return merged

    def _governance_lineage(self, packages: list[Any]) -> dict[str, Any]:
        return {
            "guidance_context_package_ids": [pkg.package_id for pkg in packages],
            "proposal_ids": self._unique([item for pkg in packages for item in pkg.governance_lineage.get("proposal_ids", [])]),
            "decision_trace_ids": self._unique([item for pkg in packages for item in pkg.governance_lineage.get("decision_trace_ids", [])]),
            "evidence_package_ids": self._unique([item for pkg in packages for item in pkg.governance_lineage.get("evidence_package_ids", [])]),
        }

    def _persist(self, package: ArchitectureWorkContextPackage) -> None:
        path = self._path(package.work_context_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("architecture_work_context_package_is_immutable")
        path.write_text(json.dumps(package.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        packages = []
        for path in self.root.glob("WORKCTX-*/package.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            packages.append({"work_context_id": data.get("work_context_id"), "project_id": data.get("project_id"), "created_at": data.get("created_at"), "work_summary": data.get("work_summary"), "resolved_architecture_ids": data.get("affected_scope", {}).get("architecture_ids", [])})
        packages.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        (self.root / "index.json").write_text(json.dumps({"packages": packages, "count": len(packages)}, indent=2, sort_keys=True), encoding="utf-8")

    def _path(self, work_context_id: str) -> Path:
        return self.root / str(work_context_id) / "package.json"

    @staticmethod
    def _unique(items: list[Any]) -> list[str]:
        return list(dict.fromkeys([str(item) for item in items if item]))
