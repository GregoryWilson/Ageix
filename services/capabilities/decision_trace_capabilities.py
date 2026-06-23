from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.decision_trace_service import DecisionTraceService


def register_capabilities(repo_root: Path):
    def requester(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": str(arguments.get("session_id") or ""),
            "agent_id": str(arguments.get("agent_id") or ""),
            "project_id": str(arguments.get("project_id") or ""),
            "client_id": arguments.get("client_id"),
            "participant_id": arguments.get("participant_id"),
        }

    def trace_create(arguments: dict[str, Any]) -> dict[str, Any]:
        service = DecisionTraceService(repo_root)
        trace = service.create_trace(
            decision_summary=str(arguments.get("decision_summary") or ""),
            outcome=str(arguments.get("outcome") or ""),
            requester_identity=requester(arguments),
            decision_id=arguments.get("decision_id"),
            decision_type=str(arguments.get("decision_type") or "governance"),
            proposal_id=arguments.get("proposal_id"),
            evidence_package_ids=arguments.get("evidence_package_ids") or [],
            consultation_ids=arguments.get("consultation_ids") or [],
            validation_ids=arguments.get("validation_ids") or [],
            repository_snapshot=arguments.get("repository_snapshot") or {},
            reason=str(arguments.get("reason") or ""),
            outcome_metadata=arguments.get("outcome_metadata") or {},
            related_entities=arguments.get("related_entities") or {},
            metadata=arguments.get("metadata") or {},
        )
        return {"success": True, "result": trace.model_dump(), "metadata": {"request_mode": "decision_trace_create", "append_only": True}, "error": None}

    def trace_get(arguments: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(arguments.get("trace_id") or "")
        if not trace_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "trace_id_required"}
        result = DecisionTraceService(repo_root).get_trace(
            trace_id,
            requester_identity=requester(arguments),
            include_freshness=bool(arguments.get("include_freshness", True)),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "decision_trace_get", "trace_id": trace_id}, "error": None}

    def trace_details(arguments: dict[str, Any]) -> dict[str, Any]:
        return trace_get(arguments)

    def trace_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = DecisionTraceService(repo_root).list_traces(
            requester_identity=requester(arguments),
            limit=arguments.get("limit"),
            offset=arguments.get("offset"),
            decision_id=arguments.get("decision_id"),
            proposal_id=arguments.get("proposal_id"),
            evidence_package_id=arguments.get("evidence_package_id"),
            outcome=arguments.get("outcome"),
            summary_contains=arguments.get("summary_contains"),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "decision_trace_list"}, "error": None}

    def trace_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        result = DecisionTraceService(repo_root).list_traces(
            requester_identity=requester(arguments),
            limit=arguments.get("limit"),
            offset=arguments.get("offset"),
            decision_id=arguments.get("decision_id"),
            proposal_id=arguments.get("proposal_id"),
            evidence_package_id=arguments.get("evidence_package_id"),
            outcome=arguments.get("outcome"),
            summary_contains=arguments.get("summary_contains") or query or None,
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "decision_trace_search"}, "error": None}

    def package_history(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        result = DecisionTraceService(repo_root).history_for_package(package_id, requester_identity=requester(arguments))
        return {"success": True, "result": result, "metadata": {"request_mode": "decision_trace_package_history", "package_id": package_id}, "error": None}

    def trace_history(arguments: dict[str, Any]) -> dict[str, Any]:
        service = DecisionTraceService(repo_root)
        package_id = arguments.get("package_id") or arguments.get("evidence_package_id")
        if package_id:
            result = service.history_for_package(str(package_id), requester_identity=requester(arguments))
        else:
            result = service.list_traces(
                requester_identity=requester(arguments),
                limit=arguments.get("limit"),
                offset=arguments.get("offset"),
                decision_id=arguments.get("decision_id"),
                proposal_id=arguments.get("proposal_id"),
                outcome=arguments.get("outcome"),
                summary_contains=arguments.get("summary_contains"),
            )
        return {"success": True, "result": result, "metadata": {"request_mode": "decision_trace_history"}, "error": None}

    return [
        (CapabilityDefinition(
            capability_id="decision.trace.create",
            category="decision_trace",
            access_level="governed_write",
            handler="decision.trace.create",
            description="Create an append-only Chair decision trace linked to proposals, evidence, validation, and consultations.",
            requires_proposal=False,
            exposed_to_external_agents=False,
        ), trace_create),
        (CapabilityDefinition(
            capability_id="decision.trace.get",
            category="decision_trace",
            access_level="governed_read",
            handler="decision.trace.get",
            description="Retrieve one decision trace with linked evidence package summaries and current freshness awareness.",
            requires_proposal=False,
        ), trace_get),
        (CapabilityDefinition(
            capability_id="decision.trace.details",
            category="decision_trace",
            access_level="governed_read",
            handler="decision.trace.details",
            description="Retrieve one decision trace with linked evidence package summaries and current freshness awareness.",
            requires_proposal=False,
        ), trace_details),
        (CapabilityDefinition(
            capability_id="decision.trace.list",
            category="decision_trace",
            access_level="governed_read",
            handler="decision.trace.list",
            description="List project-scoped append-only decision traces with simple filters.",
            requires_proposal=False,
        ), trace_list),
        (CapabilityDefinition(
            capability_id="decision.trace.search",
            category="decision_trace",
            access_level="governed_read",
            handler="decision.trace.search",
            description="Search project-scoped append-only decision traces with simple filters.",
            requires_proposal=False,
        ), trace_search),
        (CapabilityDefinition(
            capability_id="decision.trace.package_history",
            category="decision_trace",
            access_level="governed_read",
            handler="decision.trace.package_history",
            description="Find historical decision traces that used one evidence package.",
            requires_proposal=False,
        ), package_history),
        (CapabilityDefinition(
            capability_id="decision.trace.history",
            category="decision_trace",
            access_level="governed_read",
            handler="decision.trace.history",
            description="Find historical decision traces related to a package, proposal, or decision ID.",
            requires_proposal=False,
        ), trace_history),
    ]
