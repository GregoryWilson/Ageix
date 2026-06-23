from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.architecture import (
    ArchitectureHealth,
    ArchitectureIndexEntry,
    ArchitectureMetadataCompleteness,
    ArchitectureNode,
    ArchitectureNodeStatus,
    ArchitectureNodeType,
    ArchitectureReviewerDefinition,
    ArchitectureReviewTransportMode,
)


class ArchitectureRegistryService:
    """Persistent hierarchy registry for first-class Ageix architecture artifacts."""

    VALID_CHILD_TYPES = {
        ArchitectureNodeType.PROJECT: {ArchitectureNodeType.DOMAIN},
        ArchitectureNodeType.DOMAIN: {ArchitectureNodeType.COMPONENT},
        ArchitectureNodeType.COMPONENT: set(),
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / ".ageix" / "architecture"
        self.nodes_root = self.root / "nodes"
        self.index_path = self.root / "index.json"
        self.reviewers_path = self.root / "reviewers.json"

    def upsert_node(self, node: ArchitectureNode) -> ArchitectureNode:
        node = self._normalize_node(node)
        self._validate_node(node)
        self.nodes_root.mkdir(parents=True, exist_ok=True)
        node_path = self._node_path(node.architecture_id)
        node.updated_at = datetime.now(timezone.utc).isoformat()
        node.health = self.health_for_node(node)
        node_path.write_text(json.dumps(node.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        self._rebuild_index()
        return node

    def create_node(
        self,
        *,
        project_id: str,
        name: str,
        node_type: str | ArchitectureNodeType,
        parent_id: str | None = None,
        architecture_id: str | None = None,
        node_key: str | None = None,
        path: str | None = None,
        description: str = "",
        status: str | ArchitectureNodeStatus = ArchitectureNodeStatus.ACTIVE,
        linked_evidence_package_ids: list[str] | None = None,
        linked_decision_trace_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArchitectureNode:
        parent = self.get_node(parent_id) if parent_id else None
        effective_key = node_key or self._derive_node_key(name)
        effective_path = path or (f"{parent.path}.{effective_key}" if parent else effective_key)
        node = ArchitectureNode(
            architecture_id=architecture_id or f"ARCH-{__import__('uuid').uuid4().hex[:12].upper()}",
            project_id=project_id,
            node_key=effective_key,
            path=effective_path,
            name=name,
            description=description,
            parent_id=parent_id,
            node_type=node_type if isinstance(node_type, ArchitectureNodeType) else ArchitectureNodeType(str(node_type)),
            status=status if isinstance(status, ArchitectureNodeStatus) else ArchitectureNodeStatus(str(status)),
            linked_evidence_package_ids=[str(item) for item in linked_evidence_package_ids or [] if str(item)],
            linked_decision_trace_ids=[str(item) for item in linked_decision_trace_ids or [] if str(item)],
            metadata=dict(metadata or {}),
        )
        return self.upsert_node(node)

    def list_nodes(self, *, project_id: str | None = None, node_type: str | None = None, parent_id: str | None = None) -> dict[str, Any]:
        entries = list(self._load_index().get("nodes", []))
        if project_id:
            entries = [entry for entry in entries if str(entry.get("project_id") or "") == project_id]
        if node_type:
            entries = [entry for entry in entries if str(entry.get("node_type") or "") == node_type]
        if parent_id is not None:
            entries = [entry for entry in entries if entry.get("parent_id") == parent_id]
        entries.sort(key=lambda item: (str(item.get("path") or ""), str(item.get("name") or "")))
        return {"nodes": entries, "count": len(entries)}

    def get_node(self, architecture_id_or_path: str | None) -> ArchitectureNode | None:
        if not architecture_id_or_path:
            return None
        value = str(architecture_id_or_path)
        direct = self._node_path(value)
        if direct.exists():
            return ArchitectureNode(**json.loads(direct.read_text(encoding="utf-8")))
        entry = next((item for item in self._load_index().get("nodes", []) if item.get("path") == value or item.get("node_key") == value), None)
        if entry:
            return self.get_node(str(entry.get("architecture_id")))
        return None

    def require_node(self, architecture_id_or_path: str | None) -> ArchitectureNode:
        node = self.get_node(architecture_id_or_path)
        if node is None:
            raise ValueError("architecture_node_not_found")
        return node

    def get_children(self, architecture_id_or_path: str, *, include_node: bool = False) -> dict[str, Any]:
        node = self.require_node(architecture_id_or_path)
        entries = [entry for entry in self._load_index().get("nodes", []) if entry.get("parent_id") == node.architecture_id]
        entries.sort(key=lambda item: str(item.get("path") or ""))
        result: dict[str, Any] = {"parent_id": node.architecture_id, "children": entries, "count": len(entries)}
        if include_node:
            result["node"] = node.model_dump(mode="json")
        return result

    def get_subtree(self, architecture_id_or_path: str) -> dict[str, Any]:
        node = self.require_node(architecture_id_or_path)
        index = self._load_index().get("nodes", [])
        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        for entry in index:
            parent_id = entry.get("parent_id")
            if parent_id:
                children_by_parent.setdefault(str(parent_id), []).append(entry)

        def build(current: ArchitectureNode) -> dict[str, Any]:
            child_entries = sorted(children_by_parent.get(current.architecture_id, []), key=lambda item: str(item.get("path") or ""))
            return {
                "node": current.model_dump(mode="json"),
                "children": [build(self.require_node(str(child["architecture_id"]))) for child in child_entries],
            }

        return {"root_id": node.architecture_id, "subtree": build(node)}

    def link_evidence(self, architecture_id_or_path: str, package_ids: list[str], decision_trace_ids: list[str] | None = None) -> ArchitectureNode:
        node = self.require_node(architecture_id_or_path)
        for package_id in package_ids or []:
            value = str(package_id)
            if value and value not in node.linked_evidence_package_ids:
                node.linked_evidence_package_ids.append(value)
        for trace_id in decision_trace_ids or []:
            value = str(trace_id)
            if value and value not in node.linked_decision_trace_ids:
                node.linked_decision_trace_ids.append(value)
        return self.upsert_node(node)

    def health_for_node(self, node: ArchitectureNode) -> ArchitectureHealth:
        return ArchitectureHealth(
            status="observable",
            linked_evidence_count=len(node.linked_evidence_package_ids),
            linked_decision_count=len(node.linked_decision_trace_ids),
            metadata_completeness=ArchitectureMetadataCompleteness(
                name=bool(node.name.strip()),
                description=bool(node.description.strip()),
                node_key=bool(node.node_key.strip()),
                path=bool(node.path.strip()),
                parent=node.node_type == ArchitectureNodeType.PROJECT or bool(node.parent_id),
            ),
        )

    def default_reviewers(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "reviewers": [
                ArchitectureReviewerDefinition(
                    reviewer_id="lex",
                    provider="openai",
                    role="cloud_architect",
                    enabled=True,
                    transport_mode=ArchitectureReviewTransportMode.MCP_CONTEXTUAL,
                ).model_dump(mode="json"),
                ArchitectureReviewerDefinition(
                    reviewer_id="claude",
                    provider="anthropic",
                    role="cloud_architect",
                    enabled=False,
                    transport_mode=ArchitectureReviewTransportMode.API_PACKET,
                ).model_dump(mode="json"),
                ArchitectureReviewerDefinition(
                    reviewer_id="gemini",
                    provider="google",
                    role="cloud_architect",
                    enabled=False,
                    transport_mode=ArchitectureReviewTransportMode.API_PACKET,
                ).model_dump(mode="json"),
                ArchitectureReviewerDefinition(
                    reviewer_id="local_architect",
                    provider="ollama",
                    role="cloud_architect",
                    enabled=False,
                    transport_mode=ArchitectureReviewTransportMode.API_PACKET,
                ).model_dump(mode="json"),
            ],
        }

    def ensure_reviewers(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.reviewers_path.exists():
            payload = self.default_reviewers()
            self.reviewers_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return json.loads(self.reviewers_path.read_text(encoding="utf-8"))

    def seed_official_ageix_architecture(self) -> dict[str, Any]:
        if self.get_node("Ageix"):
            return {"seeded": False, "reason": "official_ageix_architecture_already_exists", "nodes": self.list_nodes(project_id="Ageix")["nodes"]}
        evidence_ids = self._available_evidence_ids()
        first = evidence_ids[:1]
        second = evidence_ids[1:2]
        project = self.create_node(project_id="Ageix", architecture_id="ARCH-AGEIX-PROJECT", name="Ageix", node_key="Ageix", path="Ageix", node_type="project", description="The official Ageix local-first AI gateway project architecture root.", linked_evidence_package_ids=first, metadata={"official": True, "seeded_by": "sprint_18_0"})
        domains = [
            ("Governance", "Governance", "Decision, proposal, trust boundary, and Chair authority capabilities."),
            ("Evidence", "Evidence", "Evidence planning, package lifecycle, freshness, lineage, and retrieval capabilities."),
            ("Consultation", "Consultation", "External advisory and consultation workflows around proposals and decisions."),
            ("MCP Platform", "MCPPlatform", "External MCP surface, tool discovery, facade execution, transport, and authentication."),
            ("Validation", "Validation", "Validation agent, validation evidence, smoke coverage, and readiness checks."),
            ("Architecture", "Architecture", "Architecture hierarchy, registry, retrieval, and future architecture governance foundations."),
        ]
        created = [project]
        domain_nodes: dict[str, ArchitectureNode] = {}
        for name, key, description in domains:
            domain = self.create_node(project_id="Ageix", architecture_id=f"ARCH-AGEIX-{key.upper()}", name=name, node_key=key, parent_id=project.architecture_id, node_type="domain", description=description, linked_evidence_package_ids=second if name in {"Evidence", "MCP Platform"} else [], metadata={"official": True, "seeded_by": "sprint_18_0"})
            domain_nodes[name] = domain
            created.append(domain)
        components = {
            "Governance": ["Proposals", "Chair Review", "Decision Trace", "Trust Boundaries"],
            "Evidence": ["Evidence Planning", "Evidence Packages", "Freshness", "Reuse and Lineage", "MCP Evidence Access"],
            "Consultation": ["External Consultation", "Proposal Consultation", "Advisor Feedback"],
            "MCP Platform": ["Tool Registry", "Capability Facade", "Transport Bridge", "OAuth JWT Auth"],
            "Validation": ["Validation Agent", "Validation Profiles", "Smoke Evidence"],
            "Architecture": ["Architecture Registry", "Hierarchy Retrieval", "Health Stub"],
        }
        for domain_name, component_names in components.items():
            parent = domain_nodes[domain_name]
            for component_name in component_names:
                key = self._derive_node_key(component_name)
                created.append(self.create_node(project_id="Ageix", architecture_id=f"ARCH-AGEIX-{parent.node_key.upper()}-{key.upper()}", name=component_name, node_key=key, parent_id=parent.architecture_id, node_type="component", description=f"{component_name} component within the {domain_name} domain.", linked_evidence_package_ids=first if component_name in {"MCP Evidence Access", "Evidence Packages"} else [], metadata={"official": True, "seeded_by": "sprint_18_0"}))
        self.ensure_reviewers()
        return {"seeded": True, "created_count": len(created), "nodes": [node.model_dump(mode="json") for node in created]}

    def _normalize_node(self, node: ArchitectureNode) -> ArchitectureNode:
        if node.parent_id:
            parent = self.require_node(node.parent_id)
            node.project_id = parent.project_id
            if not node.path.startswith(parent.path + "."):
                node.path = f"{parent.path}.{node.node_key}"
        node.linked_evidence_package_ids = list(dict.fromkeys(str(item) for item in node.linked_evidence_package_ids if str(item)))
        node.linked_decision_trace_ids = list(dict.fromkeys(str(item) for item in node.linked_decision_trace_ids if str(item)))
        return node

    def _validate_node(self, node: ArchitectureNode) -> None:
        if node.parent_id:
            parent = self.require_node(node.parent_id)
            if node.node_type not in self.VALID_CHILD_TYPES[parent.node_type]:
                raise ValueError("invalid_architecture_hierarchy_relationship")
            if parent.project_id != node.project_id:
                raise ValueError("architecture_parent_project_mismatch")
        elif node.node_type != ArchitectureNodeType.PROJECT:
            raise ValueError("non_project_architecture_node_requires_parent")
        for entry in self._load_index().get("nodes", []):
            if entry.get("architecture_id") == node.architecture_id:
                continue
            if entry.get("project_id") == node.project_id and entry.get("path") == node.path:
                raise ValueError("duplicate_architecture_path")

    def _rebuild_index(self) -> None:
        nodes = []
        child_map: dict[str, list[str]] = {}
        self.nodes_root.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.nodes_root.glob("ARCH-*.json")):
            node = ArchitectureNode(**json.loads(path.read_text(encoding="utf-8")))
            if node.parent_id:
                child_map.setdefault(node.parent_id, []).append(node.architecture_id)
            nodes.append(node)
        entries = []
        for node in sorted(nodes, key=lambda item: item.path):
            entry = ArchitectureIndexEntry(
                architecture_id=node.architecture_id,
                project_id=node.project_id,
                node_key=node.node_key,
                path=node.path,
                name=node.name,
                node_type=node.node_type,
                status=node.status,
                parent_id=node.parent_id,
                child_ids=sorted(child_map.get(node.architecture_id, [])),
                linked_evidence_count=len(node.linked_evidence_package_ids),
                linked_decision_count=len(node.linked_decision_trace_ids),
                description_state=node.description_state,
                updated_at=node.updated_at,
            )
            entries.append(entry.model_dump(mode="json"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps({"schema_version": 1, "nodes": entries}, indent=2, sort_keys=True), encoding="utf-8")

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": 1, "nodes": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _node_path(self, architecture_id: str) -> Path:
        return self.nodes_root / f"{architecture_id}.json"

    def _derive_node_key(self, name: str) -> str:
        return "".join(part[:1].upper() + part[1:] for part in str(name).replace("/", " ").replace("-", " ").split())

    def _available_evidence_ids(self) -> list[str]:
        path = self.repo_root / ".ageix" / "evidence_packages" / "index.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [str(item.get("package_id")) for item in data.get("packages", []) if item.get("package_id")]
        except Exception:
            return []
