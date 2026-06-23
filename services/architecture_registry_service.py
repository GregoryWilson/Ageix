from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from models.architecture import (
    ArchitectureContextStatus,
    ArchitectureCoverage,
    ArchitectureCoverageStatus,
    ArchitectureDecisionStatus,
    ArchitectureDescriptionState,
    ArchitectureDescriptionStatus,
    ArchitectureEvidenceStatus,
    ArchitectureFreshnessStatus,
    ArchitectureHealth,
    ArchitectureIndexEntry,
    ArchitectureMetadataCompleteness,
    ArchitectureRegistrationStatus,
    ArchitectureReviewStatus,
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
        metadata_completeness = ArchitectureMetadataCompleteness(
            name=bool(node.name.strip()),
            description=bool(node.description.strip()),
            node_key=bool(node.node_key.strip()),
            path=bool(node.path.strip()),
            parent=node.node_type == ArchitectureNodeType.PROJECT or bool(node.parent_id),
        )
        hierarchy_status = self._hierarchy_status(node)
        description_status = self._description_status(node)
        evidence_status = ArchitectureEvidenceStatus.PRESENT if node.linked_evidence_package_ids else ArchitectureEvidenceStatus.MISSING
        decision_status = ArchitectureDecisionStatus.PRESENT if node.linked_decision_trace_ids else ArchitectureDecisionStatus.NONE
        context_status = self._context_status(node)
        freshness_status = self._freshness_status(node)
        review_status = ArchitectureReviewStatus.REVIEWED if node.last_reviewed_at or node.review_count > 0 else ArchitectureReviewStatus.NEVER_REVIEWED
        statuses = [
            hierarchy_status,
            description_status.value,
            evidence_status.value,
            decision_status.value,
            context_status.value,
            freshness_status.value,
            review_status.value,
        ]
        status = "complete" if all(value in {"valid", "complete", "present", "available", "fresh", "reviewed"} for value in statuses) else "partial"
        if hierarchy_status != "valid":
            status = "invalid"
        return ArchitectureHealth(
            architecture_id=node.architecture_id,
            status=status,
            hierarchy_status=hierarchy_status,
            coverage_status=ArchitectureCoverageStatus.COMPLETE_CURRENT_STATE if hierarchy_status == "valid" else ArchitectureCoverageStatus.PARTIAL,
            description_status=description_status,
            evidence_status=evidence_status,
            decision_status=decision_status,
            review_status=review_status,
            context_status=context_status,
            freshness_status=freshness_status,
            registration_status=ArchitectureRegistrationStatus.REGISTERED,
            linked_evidence_count=len(node.linked_evidence_package_ids),
            linked_decision_count=len(node.linked_decision_trace_ids),
            review_count=max(0, int(node.review_count or 0)),
            metadata_completeness=metadata_completeness,
            metadata={
                "deterministic": True,
                "no_ai_scoring": True,
                "freshness_days": self._freshness_days(node.project_id),
                "context_failure_scope": "context_status_only",
            },
        )

    def get_health(self, architecture_id_or_path: str) -> dict[str, Any]:
        node = self.require_node(architecture_id_or_path)
        health = self.health_for_node(node)
        return {
            "architecture_id": node.architecture_id,
            "path": node.path,
            "project_id": node.project_id,
            "health": health.model_dump(mode="json"),
        }

    def get_coverage(self, *, project_id: str) -> ArchitectureCoverage:
        entries = [entry for entry in self._load_index().get("nodes", []) if str(entry.get("project_id") or "") == project_id]
        known_projects = len([entry for entry in entries if entry.get("node_type") == ArchitectureNodeType.PROJECT.value])
        known_domains = len([entry for entry in entries if entry.get("node_type") == ArchitectureNodeType.DOMAIN.value])
        known_components = len([entry for entry in entries if entry.get("node_type") == ArchitectureNodeType.COMPONENT.value])
        mapped_projects = len([entry for entry in entries if entry.get("node_type") == ArchitectureNodeType.PROJECT.value and entry.get("path")])
        mapped_domains = 0
        mapped_components = 0
        for entry in entries:
            node_type = entry.get("node_type")
            if node_type not in {ArchitectureNodeType.DOMAIN.value, ArchitectureNodeType.COMPONENT.value}:
                continue
            if entry.get("parent_id") and entry.get("path"):
                if node_type == ArchitectureNodeType.DOMAIN.value:
                    mapped_domains += 1
                elif node_type == ArchitectureNodeType.COMPONENT.value:
                    mapped_components += 1
        total_known = known_projects + known_domains + known_components
        total_mapped = mapped_projects + mapped_domains + mapped_components
        ratio = (total_mapped / total_known) if total_known else 0.0
        if total_known == 0:
            coverage_status = ArchitectureCoverageStatus.UNKNOWN
        elif ratio >= 1.0:
            coverage_status = ArchitectureCoverageStatus.COMPLETE_CURRENT_STATE
        elif ratio >= 0.5:
            coverage_status = ArchitectureCoverageStatus.SUBSTANTIAL
        else:
            coverage_status = ArchitectureCoverageStatus.PARTIAL
        return ArchitectureCoverage(
            project_id=project_id,
            coverage_status=coverage_status,
            known_domains=known_domains,
            mapped_domains=mapped_domains,
            known_components=known_components,
            mapped_components=mapped_components,
            known_projects=known_projects,
            mapped_projects=mapped_projects,
            discovery_status=ArchitectureRegistrationStatus.UNKNOWN,
            metrics={
                "known_total": total_known,
                "mapped_total": total_mapped,
                "mapped_ratio": ratio,
                "coverage_source": "architecture_registry",
            },
            metadata={
                "deterministic": True,
                "discovery_hook_present": True,
                "repository_wide_discovery_performed": False,
            },
        )


    def _hierarchy_status(self, node: ArchitectureNode) -> str:
        try:
            self._validate_node(node)
            return "valid"
        except Exception as exc:
            return f"invalid:{exc}"

    def _description_status(self, node: ArchitectureNode) -> ArchitectureDescriptionStatus:
        if node.description_state == ArchitectureDescriptionState.APPROVED:
            return ArchitectureDescriptionStatus.COMPLETE
        if node.description.strip():
            return ArchitectureDescriptionStatus.PARTIAL
        return ArchitectureDescriptionStatus.MISSING

    def _context_status(self, node: ArchitectureNode) -> ArchitectureContextStatus:
        try:
            from services.architecture_context_service import ArchitectureContextService

            ArchitectureContextService(self.repo_root).build_context(node.architecture_id, include_detail=False)
            return ArchitectureContextStatus.AVAILABLE
        except Exception:
            return ArchitectureContextStatus.FAILED

    def _freshness_status(self, node: ArchitectureNode) -> ArchitectureFreshnessStatus:
        threshold_days = self._freshness_days(node.project_id)
        newest_activity = self._parse_datetime(node.updated_at)
        evidence_state = self._linked_evidence_state(node.linked_evidence_package_ids)
        if evidence_state["has_stale"]:
            return ArchitectureFreshnessStatus.STALE
        if evidence_state["newest_activity"] and (newest_activity is None or evidence_state["newest_activity"] > newest_activity):
            newest_activity = evidence_state["newest_activity"]
        for value in node.linked_decision_trace_ids:
            activity = self._decision_activity(str(value))
            if activity and (newest_activity is None or activity > newest_activity):
                newest_activity = activity
        if not node.linked_evidence_package_ids and not node.linked_decision_trace_ids and not node.updated_at:
            return ArchitectureFreshnessStatus.UNKNOWN
        if newest_activity is None:
            return ArchitectureFreshnessStatus.UNKNOWN
        return ArchitectureFreshnessStatus.STALE if datetime.now(timezone.utc) - newest_activity > timedelta(days=threshold_days) else ArchitectureFreshnessStatus.FRESH

    def _freshness_days(self, project_id: str) -> int:
        config_path = self.repo_root / ".ageix" / "config" / "architecture.json"
        default_days = 30
        if not config_path.exists():
            return default_days
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            by_project = data.get("architecture_freshness_days_by_project") or {}
            value = by_project.get(project_id, data.get("architecture_freshness_days", default_days))
            return max(1, int(value))
        except Exception:
            return default_days

    def _linked_evidence_state(self, package_ids: list[str]) -> dict[str, Any]:
        index_path = self.repo_root / ".ageix" / "evidence_packages" / "index.json"
        result = {"has_stale": False, "newest_activity": None}
        if not package_ids or not index_path.exists():
            return result
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8")).get("packages", [])
        except Exception:
            return result
        by_id = {str(entry.get("package_id")): entry for entry in entries}
        for package_id in package_ids:
            entry = by_id.get(str(package_id))
            if not entry:
                continue
            result["has_stale"] = result["has_stale"] or bool(entry.get("stale")) or str(entry.get("freshness_status") or "") not in {"", "unchanged"}
            for key in ("last_freshness_check_at", "last_recommended_at", "last_used_in_decision_at", "created_at"):
                activity = self._parse_datetime(entry.get(key))
                if activity and (result["newest_activity"] is None or activity > result["newest_activity"]):
                    result["newest_activity"] = activity
        return result

    def _decision_activity(self, trace_id: str) -> datetime | None:
        index_path = self.repo_root / ".ageix" / "decision_traces" / "index.json"
        if not index_path.exists():
            return None
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8")).get("traces", [])
        except Exception:
            return None
        entry = next((item for item in entries if str(item.get("trace_id")) == trace_id), None)
        if not entry:
            return None
        return self._parse_datetime(entry.get("updated_at") or entry.get("created_at"))

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

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
            upgraded = self._ensure_official_ageix_baseline_v1()
            return {"seeded": False, "reason": "official_ageix_architecture_already_exists", "upgraded": upgraded, "nodes": self.list_nodes(project_id="Ageix")["nodes"]}
        evidence_ids = self._available_evidence_ids()
        first = evidence_ids[:1]
        second = evidence_ids[1:2]
        project = self.create_node(project_id="Ageix", architecture_id="ARCH-AGEIX-PROJECT", name="Ageix", node_key="Ageix", path="Ageix", node_type="project", description="The official Ageix local-first AI gateway project architecture root.", linked_evidence_package_ids=first, metadata={"official": True, "seeded_by": "sprint_18_2_baseline_v1"})
        domains = [
            ("Governance", "Governance", "Decision, trust boundary, and Chair authority capabilities."),
            ("Evidence", "Evidence", "Evidence planning, package lifecycle, freshness, lineage, and retrieval capabilities."),
            ("Proposal System", "ProposalSystem", "Governed proposal submission, orchestration, status, and lifecycle capabilities."),
            ("Consultation System", "ConsultationSystem", "External advisory and consultation workflows around proposals and decisions."),
            ("MCP Platform", "MCPPlatform", "External MCP surface, tool discovery, facade execution, and transport capabilities."),
            ("Authentication", "Authentication", "OAuth, JWT, JWKS, scope mapping, and authenticated client identity capabilities."),
            ("Validation", "Validation", "Validation agent, validation evidence, smoke coverage, and readiness checks."),
            ("Architecture", "Architecture", "Architecture hierarchy, registry, retrieval, health, and future architecture governance foundations."),
        ]
        created = [project]
        domain_nodes: dict[str, ArchitectureNode] = {}
        for name, key, description in domains:
            domain = self.create_node(project_id="Ageix", architecture_id=f"ARCH-AGEIX-{key.upper()}", name=name, node_key=key, parent_id=project.architecture_id, node_type="domain", description=description, linked_evidence_package_ids=second if name in {"Evidence", "MCP Platform"} else [], metadata={"official": True, "seeded_by": "sprint_18_2_baseline_v1"})
            domain_nodes[name] = domain
            created.append(domain)
        components = {
            "Governance": ["Chair Review", "Decision Trace", "Trust Boundaries", "Approval Controls"],
            "Evidence": ["Evidence Planning", "Evidence Packages", "Freshness", "Reuse and Lineage", "MCP Evidence Access"],
            "Proposal System": ["Proposal Submission", "Proposal Status", "Proposal Orchestration", "Proposal Governance"],
            "Consultation System": ["External Consultation", "Proposal Consultation", "Advisor Feedback"],
            "MCP Platform": ["Tool Registry", "Capability Facade", "Transport Bridge", "MCP Discovery"],
            "Authentication": ["OAuth", "JWT Validation", "JWKS Discovery", "Scope Mapping"],
            "Validation": ["Validation Agent", "Validation Profiles", "Smoke Evidence"],
            "Architecture": ["Architecture Registry", "Hierarchy Retrieval", "Architecture Context", "Architecture Health"],
        }
        for domain_name, component_names in components.items():
            parent = domain_nodes[domain_name]
            for component_name in component_names:
                key = self._derive_node_key(component_name)
                created.append(self.create_node(project_id="Ageix", architecture_id=f"ARCH-AGEIX-{parent.node_key.upper()}-{key.upper()}", name=component_name, node_key=key, parent_id=parent.architecture_id, node_type="component", description=f"{component_name} component within the {domain_name} domain.", linked_evidence_package_ids=first if component_name in {"MCP Evidence Access", "Evidence Packages"} else [], metadata={"official": True, "seeded_by": "sprint_18_2_baseline_v1"}))
        self.ensure_reviewers()
        return {"seeded": True, "created_count": len(created), "nodes": [node.model_dump(mode="json") for node in created]}


    def _ensure_official_ageix_baseline_v1(self) -> dict[str, Any]:
        project = self.require_node("Ageix")
        changed: list[str] = []

        def ensure_domain(name: str, key: str, description: str) -> ArchitectureNode:
            existing = self.get_node(f"Ageix.{key}") or self.get_node(name)
            if existing:
                updated = False
                if existing.name != name:
                    existing.name = name; updated = True
                if existing.node_key != key:
                    existing.node_key = key; updated = True
                if existing.path != f"Ageix.{key}":
                    existing.path = f"Ageix.{key}"; updated = True
                if existing.description != description:
                    existing.description = description; updated = True
                existing.metadata.setdefault("official", True)
                existing.metadata["seeded_by"] = "sprint_18_2_baseline_v1"
                if updated:
                    changed.append(existing.architecture_id)
                return self.upsert_node(existing)
            changed.append(f"domain:{key}")
            return self.create_node(project_id="Ageix", architecture_id=f"ARCH-AGEIX-{key.upper()}", name=name, node_key=key, parent_id=project.architecture_id, node_type="domain", description=description, metadata={"official": True, "seeded_by": "sprint_18_2_baseline_v1"})

        domains = {
            "Governance": ensure_domain("Governance", "Governance", "Decision, trust boundary, and Chair authority capabilities."),
            "Evidence": ensure_domain("Evidence", "Evidence", "Evidence planning, package lifecycle, freshness, lineage, and retrieval capabilities."),
            "Proposal System": ensure_domain("Proposal System", "ProposalSystem", "Governed proposal submission, orchestration, status, and lifecycle capabilities."),
            "Consultation System": ensure_domain("Consultation System", "ConsultationSystem", "External advisory and consultation workflows around proposals and decisions."),
            "MCP Platform": ensure_domain("MCP Platform", "MCPPlatform", "External MCP surface, tool discovery, facade execution, and transport capabilities."),
            "Authentication": ensure_domain("Authentication", "Authentication", "OAuth, JWT, JWKS, scope mapping, and authenticated client identity capabilities."),
            "Validation": ensure_domain("Validation", "Validation", "Validation agent, validation evidence, smoke coverage, and readiness checks."),
            "Architecture": ensure_domain("Architecture", "Architecture", "Architecture hierarchy, registry, retrieval, health, and future architecture governance foundations."),
        }
        components = {
            "Governance": ["Chair Review", "Decision Trace", "Trust Boundaries", "Approval Controls"],
            "Evidence": ["Evidence Planning", "Evidence Packages", "Freshness", "Reuse and Lineage", "MCP Evidence Access"],
            "Proposal System": ["Proposal Submission", "Proposal Status", "Proposal Orchestration", "Proposal Governance"],
            "Consultation System": ["External Consultation", "Proposal Consultation", "Advisor Feedback"],
            "MCP Platform": ["Tool Registry", "Capability Facade", "Transport Bridge", "MCP Discovery"],
            "Authentication": ["OAuth", "JWT Validation", "JWKS Discovery", "Scope Mapping"],
            "Validation": ["Validation Agent", "Validation Profiles", "Smoke Evidence"],
            "Architecture": ["Architecture Registry", "Hierarchy Retrieval", "Architecture Context", "Architecture Health"],
        }
        # Rename the 18.1 placeholder if present so existing repositories get the official v1 health node.
        placeholder = self.get_node("Ageix.Architecture.HealthStub")
        if placeholder:
            placeholder.name = "Architecture Health"
            placeholder.node_key = "ArchitectureHealth"
            placeholder.path = "Ageix.Architecture.ArchitectureHealth"
            placeholder.description = "Architecture Health component within the Architecture domain."
            placeholder.metadata["official"] = True
            placeholder.metadata["seeded_by"] = "sprint_18_2_baseline_v1"
            self.upsert_node(placeholder)
            changed.append(placeholder.architecture_id)
        for domain_name, component_names in components.items():
            parent = domains[domain_name]
            for component_name in component_names:
                key = self._derive_node_key(component_name)
                path = f"{parent.path}.{key}"
                if self.get_node(path):
                    continue
                changed.append(f"component:{path}")
                self.create_node(project_id="Ageix", architecture_id=f"ARCH-AGEIX-{parent.node_key.upper()}-{key.upper()}", name=component_name, node_key=key, parent_id=parent.architecture_id, node_type="component", description=f"{component_name} component within the {domain_name} domain.", metadata={"official": True, "seeded_by": "sprint_18_2_baseline_v1"})
        self._rebuild_index()
        return {"baseline_version": 1, "changed_count": len(changed), "changed": changed}

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
