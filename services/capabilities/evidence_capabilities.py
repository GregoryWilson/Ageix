from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from models.evidence_access_proposal import EvidenceAccessProposal
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_lifecycle_service import EvidencePackageLifecycleService


def register_capabilities(repo_root: Path):

    def requester(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": str(arguments.get("session_id") or ""),
            "agent_id": str(arguments.get("agent_id") or ""),
            "project_id": str(arguments.get("project_id") or ""),
            "client_id": arguments.get("client_id"),
            "participant_id": arguments.get("participant_id"),
        }

    def package_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = EvidencePackageLifecycleService(repo_root).list_packages(
            requester_identity=requester(arguments),
            limit=arguments.get("limit"),
            offset=arguments.get("offset"),
            proposal_id=arguments.get("proposal_id"),
            evidence_plan_id=arguments.get("evidence_plan_id"),
            stale=arguments.get("stale"),
            objective_contains=arguments.get("objective_contains"),
            context_contains=arguments.get("context_contains"),
            created_before=arguments.get("created_before"),
            created_after=arguments.get("created_after"),
        )
        return {
            "success": True,
            "result": result,
            "metadata": {"request_mode": "package_discovery", "summary_only": True},
            "error": None,
        }

    def package_details(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        result = EvidencePackageLifecycleService(repo_root).details(package_id, requester_identity=requester(arguments))
        return {
            "success": True,
            "result": result,
            "metadata": {"request_mode": "package_details", "package_id": package_id, "contents_returned": False},
            "error": None,
        }

    def package_freshness(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        result = EvidencePackageLifecycleService(repo_root).evaluate_freshness(package_id, requester_identity=requester(arguments))
        return {
            "success": True,
            "result": result,
            "metadata": {"request_mode": "package_freshness", "package_id": package_id, "index_updated": True},
            "error": None,
        }

    def package_rehydrate(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        package = EvidencePackageLifecycleService(repo_root).rehydrate(package_id, requester_identity=requester(arguments))
        return {
            "success": True,
            "result": package.model_dump(),
            "metadata": {
                "request_mode": "package_rehydration",
                "package_id": package.package_id,
                "immutable_contents_returned": True,
                "freshness_evaluated": False,
            },
            "error": None,
        }

    def package_recommend(arguments: dict[str, Any]) -> dict[str, Any]:
        objective = str(arguments.get("objective") or "")
        if not objective:
            return {"success": False, "result": {}, "metadata": {}, "error": "objective_required"}
        result = EvidencePackageLifecycleService(repo_root).recommend(
            objective=objective,
            requester_identity=requester(arguments),
            limit=arguments.get("limit"),
            min_similarity=float(arguments.get("min_similarity") or 0.1),
        )
        return {
            "success": True,
            "result": result,
            "metadata": {"request_mode": "package_recommendation", "advisory_only": True, "visibility_filtered": True},
            "error": None,
        }

    def package_reuse(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        package = EvidencePackageLifecycleService(repo_root).reuse_package(
            package_id,
            requester_identity=requester(arguments),
            objective=arguments.get("objective"),
            lineage_type=str(arguments.get("lineage_type") or "reuse"),
            reuse_reason=str(arguments.get("reuse_reason") or "Chair approved evidence package reuse."),
            automatic_refresh=bool(arguments.get("automatic_refresh", False)),
        )
        return {
            "success": True,
            "result": package.model_dump(),
            "metadata": {
                "request_mode": "package_reuse",
                "parent_package_ids": package.parent_package_ids,
                "child_package_id": package.package_id,
                "immutable_child_created": True,
                "automatic_refresh": False,
            },
            "error": None,
        }


    def package_deprecate(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        result = EvidencePackageLifecycleService(repo_root).deprecate_package(
            package_id,
            requester_identity=requester(arguments),
            reason=str(arguments.get("reason") or "Package deprecated by governance action."),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "package_deprecation", "package_id": package_id}, "error": None}

    def package_supersede(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        replacement_id = str(arguments.get("superseded_by_package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        if not replacement_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "superseded_by_package_id_required"}
        result = EvidencePackageLifecycleService(repo_root).supersede_package(
            package_id,
            superseded_by_package_id=replacement_id,
            requester_identity=requester(arguments),
            reason=str(arguments.get("reason") or "Package superseded by replacement evidence package."),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "package_supersession", "package_id": package_id, "superseded_by_package_id": replacement_id}, "error": None}

    def package_lineage(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        result = EvidencePackageLifecycleService(repo_root).lineage(package_id, requester_identity=requester(arguments))
        return {
            "success": True,
            "result": result,
            "metadata": {"request_mode": "package_lineage", "package_id": package_id},
            "error": None,
        }

    def evidence_request(arguments: dict[str, Any]) -> dict[str, Any]:
        # Sprint 17.1: proposal_id/evidence_plan_id means fulfill an already-approved
        # intent plan. Existing explicit/intent proposal submission remains unchanged
        # when those identifiers are absent.
        if arguments.get("package_id") or arguments.get("proposal_id") or arguments.get("evidence_plan_id"):
            package = EvidenceBrokerService(repo_root).request_evidence(
                proposal_id=arguments.get("proposal_id"),
                evidence_plan_id=arguments.get("evidence_plan_id"),
                package_id=arguments.get("package_id"),
                evaluate_freshness=bool(arguments.get("evaluate_freshness", True)),
                requester_identity={
                    "session_id": str(arguments.get("session_id") or ""),
                    "agent_id": str(arguments.get("agent_id") or ""),
                    "project_id": str(arguments.get("project_id") or ""),
                    "client_id": arguments.get("client_id"),
                    "participant_id": arguments.get("participant_id"),
                },
            )
            return {
                "success": True,
                "result": package.model_dump(),
                "metadata": {
                    "proposal_type": "evidence_access",
                    "request_mode": "package_rehydration" if arguments.get("package_id") else "intent_package",
                    "evidence_broker_used": True,
                    "package_rehydrated": bool(arguments.get("package_id")),
                    "evidence_package_id": package.package_id,
                    "evidence_plan_id": package.evidence_plan_id,
                    "retrieval_confidence": package.retrieval_confidence,
                    "freshness": package.freshness.model_dump() if package.freshness else None,
                },
                "error": None,
            }

        proposal = EvidenceAccessProposal(
            session_id=str(arguments.get("session_id") or ""),
            agent_id=str(arguments.get("agent_id") or ""),
            project_id=str(arguments.get("project_id") or ""),
            objective=str(arguments.get("objective") or ""),
            reason=str(arguments.get("reason") or ""),
            request_mode=str(arguments.get("request_mode") or "explicit"),
            requested_evidence=arguments.get("requested_evidence") or [],
            target=arguments.get("target"),
            desired_outcome=arguments.get("desired_outcome"),
            intent_type=str(arguments.get("intent_type") or "unknown"),
            human_approval=arguments.get("human_approval"),
        )
        decision = EvidenceAccessProposalService(repo_root).evaluate(proposal)
        return {
            "success": decision.decision == "approved",
            "result": decision.model_dump(),
            "metadata": {
                "proposal_type": "evidence_access",
                "requires_proposal": True,
                "request_mode": proposal.request_mode,
                **decision.metadata,
            },
            "error": None if decision.decision == "approved" else decision.decision,
        }

    return [
        (CapabilityDefinition(
            capability_id="evidence.request",
            category="evidence",
            access_level="governed_read",
            handler="evidence.request",
            description="Request scoped repository evidence through a Chair-governed evidence access proposal.",
            requires_proposal=True,
        ), evidence_request),
        (CapabilityDefinition(
            capability_id="evidence.proposal.submit",
            category="evidence",
            access_level="governed_read",
            handler="evidence.proposal.submit",
            description="Submit a governed evidence-access proposal.",
            requires_proposal=True,
        ), evidence_request),
        (CapabilityDefinition(
            capability_id="evidence.package.list",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.list",
            description="List project-scoped immutable evidence package summaries from the package index.",
            requires_proposal=False,
        ), package_list),
        (CapabilityDefinition(
            capability_id="evidence.package.details",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.details",
            description="Return package metadata, freshness, counts, and provenance manifest without regenerating package contents.",
            requires_proposal=False,
        ), package_details),
        (CapabilityDefinition(
            capability_id="evidence.package.freshness",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.freshness",
            description="Evaluate content-hash freshness for one immutable evidence package and update the package index.",
            requires_proposal=False,
        ), package_freshness),
        (CapabilityDefinition(
            capability_id="evidence.package.rehydrate",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.rehydrate",
            description="Return one immutable historical evidence package by package ID without regenerating or mutating contents.",
            requires_proposal=False,
        ), package_rehydrate),
        (CapabilityDefinition(
            capability_id="evidence.package.recommend",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.recommend",
            description="Recommend visible historical evidence packages for a new objective; advisory to Chair only.",
            requires_proposal=False,
        ), package_recommend),
        (CapabilityDefinition(
            capability_id="evidence.package.reuse",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.reuse",
            description="Create a new immutable child package that records Chair-approved reuse of a visible parent package.",
            requires_proposal=False,
        ), package_reuse),
        (CapabilityDefinition(
            capability_id="evidence.package.deprecate",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.deprecate",
            description="Mark a visible package deprecated in catalog metadata without mutating package contents.",
            requires_proposal=False,
        ), package_deprecate),
        (CapabilityDefinition(
            capability_id="evidence.package.supersede",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.supersede",
            description="Mark a visible package superseded by a newer compatible package without mutating package contents.",
            requires_proposal=False,
        ), package_supersede),
        (CapabilityDefinition(
            capability_id="evidence.package.lineage",
            category="evidence",
            access_level="governed_read",
            handler="evidence.package.lineage",
            description="Return visible parent, child, ancestor, and descendant package lineage.",
            requires_proposal=False,
        ), package_lineage),
    ]
