from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ageix_mcp.facade_service import MCPFacadeService
from services.capability_registry_service import CapabilityRegistryService
from services.evidence_package_index_service import EvidencePackageIndexService


class EvidencePlatformReadinessService:
    """Validation-only Sprint 17 evidence platform closure/readiness checks."""

    READINESS_PATH = Path(".ageix") / "readiness" / "evidence_platform_readiness.json"

    REQUIRED_EVIDENCE_TOOLS = {
        "ageix.evidence.package.list",
        "ageix.evidence.package.search",
        "ageix.evidence.package.details",
        "ageix.evidence.package.retrieve",
        "ageix.evidence.package.recommend",
        "ageix.evidence.package.reuse",
        "ageix.evidence.package.lineage",
        "ageix.evidence.package.freshness",
    }
    REQUIRED_DECISION_TRACE_TOOLS = {
        "ageix.decision.trace.list",
        "ageix.decision.trace.search",
        "ageix.decision.trace.details",
        "ageix.decision.trace.history",
    }
    HIDDEN_EXTERNAL_TOOLS = {"ageix.decision.trace.create"}
    HIDDEN_EXTERNAL_CAPABILITIES = {"decision.trace.create"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.index = EvidencePackageIndexService(self.repo_root)

    def assess(self, *, write_artifact: bool = False) -> dict[str, Any]:
        index_validation = self.index.validate_index()
        entries = self.index.list_entries()
        package_health = self._package_health(entries)
        trace_health = self._decision_trace_health()
        mcp_health = self._mcp_health()
        issues = self._issues(index_validation, package_health, trace_health, mcp_health)
        ready = not issues
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform": "evidence",
            "sprint": "17.9",
            "readiness_status": "pass" if ready else "fail",
            "ready_for_architecture_hierarchy": ready,
            "validation_only": True,
            "repair_performed": False,
            "cleanup_performed": False,
            "index_validation": index_validation,
            "package_health": package_health,
            "decision_trace_health": trace_health,
            "mcp_exposure_health": mcp_health,
            "issues": issues,
            "summary": {
                "package_count": package_health["package_count"],
                "fresh_package_count": package_health["fresh_package_count"],
                "stale_package_count": package_health["stale_package_count"],
                "deprecated_package_count": package_health["deprecated_package_count"],
                "superseded_package_count": package_health["superseded_package_count"],
                "restricted_package_count": package_health["restricted_package_count"],
                "smoke_demo_cleanup_candidate_count": package_health["smoke_demo_cleanup_candidate_count"],
                "decision_trace_count": trace_health["trace_count"],
                "mcp_evidence_access": mcp_health["evidence_access_status"],
                "decision_trace_governance": mcp_health["decision_trace_governance_status"],
            },
        }
        if write_artifact:
            self.write_artifact(result)
        return result

    def write_artifact(self, result: dict[str, Any]) -> Path:
        path = self.repo_root / self.READINESS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _package_health(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        stale = [entry for entry in entries if bool(entry.get("stale")) or self._freshness_status(entry) != "unchanged"]
        deprecated = [entry for entry in entries if self._governance_status(entry) == "deprecated" or bool(self._governance(entry).get("deprecated"))]
        superseded = [entry for entry in entries if self._governance_status(entry) == "superseded" or bool(self._governance(entry).get("superseded_by_package_id"))]
        restricted = [entry for entry in entries if self._governance_status(entry) == "restricted"]
        cleanup_candidates = [entry for entry in entries if self._cleanup_eligible(entry)]
        governance_issues = self._package_governance_issues(entries)
        return {
            "package_count": len(entries),
            "fresh_package_count": len(entries) - len(stale),
            "stale_package_count": len(stale),
            "deprecated_package_count": len(deprecated),
            "superseded_package_count": len(superseded),
            "restricted_package_count": len(restricted),
            "smoke_demo_cleanup_candidate_count": len(cleanup_candidates),
            "cleanup_candidate_package_ids": [str(entry.get("package_id")) for entry in cleanup_candidates],
            "cleanup_recommendation": "manual_cleanup_available" if cleanup_candidates else "none",
            "cleanup_policy": "detect_only_no_delete",
            "governance_issue_count": len(governance_issues),
            "governance_issues": governance_issues,
        }

    def _decision_trace_health(self) -> dict[str, Any]:
        index_path = self.repo_root / ".ageix" / "decision_traces" / "index.json"
        if not index_path.exists():
            return {"trace_count": 0, "index_exists": False, "status": "pass"}
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"trace_count": 0, "index_exists": True, "status": "fail", "error": f"invalid_decision_trace_index:{exc}"}
        traces = list(payload.get("traces") or [])
        trace_ids = [str(item.get("trace_id") or "") for item in traces]
        duplicate_ids = sorted({trace_id for trace_id in trace_ids if trace_id and trace_ids.count(trace_id) > 1})
        return {
            "trace_count": len(traces),
            "index_exists": True,
            "duplicate_trace_ids": duplicate_ids,
            "status": "pass" if not duplicate_ids else "fail",
        }

    def _mcp_health(self) -> dict[str, Any]:
        facade = MCPFacadeService(self.repo_root)
        tools = facade.discover_tools(include_disabled=True, exposed_only=True)
        exposed_tool_names = {str(tool.get("tool_name") or tool.get("name") or "") for tool in tools}
        exposed_capabilities = {str(item.get("capability_id") or "") for item in facade.list_capabilities(exposed_only=True)}
        raw_create = CapabilityRegistryService(self.repo_root).lookup("decision.trace.create")
        required_tools = self.REQUIRED_EVIDENCE_TOOLS | self.REQUIRED_DECISION_TRACE_TOOLS
        missing_required_tools = sorted(required_tools - exposed_tool_names)
        forbidden_tools_visible = sorted(self.HIDDEN_EXTERNAL_TOOLS.intersection(exposed_tool_names))
        forbidden_capabilities_visible = sorted(self.HIDDEN_EXTERNAL_CAPABILITIES.intersection(exposed_capabilities))
        raw_create_exposed = bool(raw_create and raw_create.exposed_to_external_agents)
        decision_trace_ok = not forbidden_tools_visible and not forbidden_capabilities_visible and raw_create_exposed is False
        evidence_ok = not sorted(self.REQUIRED_EVIDENCE_TOOLS - exposed_tool_names)
        return {
            "status": "pass" if evidence_ok and decision_trace_ok and not missing_required_tools else "fail",
            "evidence_access_status": "pass" if evidence_ok else "fail",
            "decision_trace_governance_status": "pass" if decision_trace_ok else "fail",
            "required_tool_count": len(required_tools),
            "missing_required_tools": missing_required_tools,
            "forbidden_tools_visible": forbidden_tools_visible,
            "forbidden_capabilities_visible": forbidden_capabilities_visible,
            "decision_trace_create_registry_exposed": raw_create_exposed,
            "exposed_evidence_tool_count": len([name for name in exposed_tool_names if name.startswith("ageix.evidence.package.")]),
            "exposed_decision_trace_tool_count": len([name for name in exposed_tool_names if name.startswith("ageix.decision.trace.")]),
        }

    def _issues(
        self,
        index_validation: dict[str, Any],
        package_health: dict[str, Any],
        trace_health: dict[str, Any],
        mcp_health: dict[str, Any],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if index_validation.get("status") != "pass":
            issues.append({"code": "package_index_invalid", "details": index_validation})
        if package_health.get("governance_issue_count", 0):
            issues.append({"code": "package_governance_invalid", "details": package_health.get("governance_issues", [])})
        if trace_health.get("status") != "pass":
            issues.append({"code": "decision_trace_index_invalid", "details": trace_health})
        if mcp_health.get("status") != "pass":
            issues.append({"code": "mcp_evidence_exposure_invalid", "details": mcp_health})
        return issues

    def _package_governance_issues(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for entry in entries:
            package_id = str(entry.get("package_id") or "")
            governance = self._governance(entry)
            status = self._governance_status(entry)
            if status == "superseded" and not governance.get("superseded_by_package_id"):
                issues.append({"package_id": package_id, "code": "superseded_without_replacement"})
            if status == "deprecated" and governance.get("deprecated") is False:
                issues.append({"package_id": package_id, "code": "deprecated_status_without_flag"})
            score = governance.get("governance_score")
            if score is not None and not 0 <= int(score) <= 120:
                issues.append({"package_id": package_id, "code": "governance_score_out_of_range", "score": score})
        return issues

    def _governance(self, entry: dict[str, Any]) -> dict[str, Any]:
        return dict(entry.get("governance") or {})

    def _governance_status(self, entry: dict[str, Any]) -> str:
        status = self._governance(entry).get("status") or entry.get("governance_status") or "active"
        return str(getattr(status, "value", status)).lower()

    def _freshness_status(self, entry: dict[str, Any]) -> str:
        status = entry.get("freshness_status") or "unchanged"
        return str(getattr(status, "value", status)).lower()

    def _cleanup_eligible(self, entry: dict[str, Any]) -> bool:
        lifecycle = dict(entry.get("lifecycle") or {})
        return lifecycle.get("artifact_type") == "smoke_demo" and bool(lifecycle.get("cleanup_eligible"))
