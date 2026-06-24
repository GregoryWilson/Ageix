from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.architecture_context_service import ArchitectureContextService
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_revision_service import ArchitectureRevisionService


def register_capabilities(repo_root: Path):
    def service() -> ArchitectureRegistryService:
        return ArchitectureRegistryService(repo_root)

    def revision_service() -> ArchitectureRevisionService:
        return ArchitectureRevisionService(repo_root)

    def adr_service() -> ArchitectureDecisionRecordService:
        return ArchitectureDecisionRecordService(repo_root)

    def guidance_service() -> ArchitectureGuidanceService:
        return ArchitectureGuidanceService(repo_root)

    def guidance_context_service() -> ArchitectureGuidanceContextService:
        return ArchitectureGuidanceContextService(repo_root)

    def architecture_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().list_nodes(
            project_id=str(arguments.get("project_id") or "") or None,
            node_type=str(arguments.get("node_type") or "") or None,
            parent_id=arguments.get("parent_id"),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_list"}, "error": None}

    def architecture_details(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        node = service().require_node(identifier)
        return {"success": True, "result": node.model_dump(mode="json"), "metadata": {"request_mode": "architecture_details", "architecture_id": node.architecture_id}, "error": None}

    def architecture_children(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        result = service().get_children(identifier, include_node=bool(arguments.get("include_node", False)))
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_children"}, "error": None}

    def architecture_subtree(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        result = service().get_subtree(identifier)
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_subtree"}, "error": None}


    def architecture_context(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        requester = {
            "session_id": str(arguments.get("session_id") or ""),
            "agent_id": str(arguments.get("agent_id") or ""),
            "project_id": str(arguments.get("project_id") or ""),
            "client_id": arguments.get("client_id"),
            "participant_id": arguments.get("participant_id"),
        }
        context = ArchitectureContextService(repo_root).build_context(
            identifier,
            include_detail=bool(arguments.get("include_detail", False)),
            requester_identity=requester,
        )
        return {"success": True, "result": context.model_dump(mode="json"), "metadata": {"request_mode": "architecture_context", "architecture_id": context.architecture_id}, "error": None}

    def architecture_description_draft(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        description = ArchitectureContextService(repo_root).create_description(
            identifier,
            purpose=str(arguments.get("purpose") or ""),
            responsibilities=arguments.get("responsibilities") or [],
            boundaries=arguments.get("boundaries") or [],
            open_questions=arguments.get("open_questions") or [],
            detailed_description=str(arguments.get("detailed_description") or ""),
            source_actor=str(arguments.get("source_actor") or "architect_worker"),
            metadata=arguments.get("metadata") or {},
        )
        return {"success": True, "result": description.model_dump(mode="json"), "metadata": {"request_mode": "architecture_description_draft", "description_id": description.description_id}, "error": None}

    def architecture_description_approve(arguments: dict[str, Any]) -> dict[str, Any]:
        description_id = str(arguments.get("description_id") or "")
        if not description_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "description_id_required"}
        description = ArchitectureContextService(repo_root).approve_description(description_id, approved_by=str(arguments.get("approved_by") or "chair"))
        return {"success": True, "result": description.model_dump(mode="json"), "metadata": {"request_mode": "architecture_description_approve", "description_id": description.description_id}, "error": None}


    def architecture_health(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        result = service().get_health(identifier)
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_health", "architecture_id": result["architecture_id"], "deterministic": True}, "error": None}

    def architecture_coverage(arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = str(arguments.get("project_id") or "")
        if not project_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "project_id_required"}
        coverage = service().get_coverage(project_id=project_id)
        return {"success": True, "result": coverage.model_dump(mode="json"), "metadata": {"request_mode": "architecture_coverage", "project_id": project_id, "deterministic": True}, "error": None}

    def architecture_baseline_validate(arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = str(arguments.get("project_id") or "Ageix")
        result = service().validate_baseline(project_id=project_id)
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_baseline_validate", "project_id": project_id, "deterministic": True}, "error": None}


    def architecture_review_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        try:
            review = service().submit_review(
                architecture_id_or_path=identifier,
                reviewer_id=str(arguments.get("agent_id") or arguments.get("reviewer_id") or ""),
                project_id=str(arguments.get("project_id") or ""),
                summary=str(arguments.get("summary") or ""),
                rationale=str(arguments.get("rationale") or ""),
                no_findings=bool(arguments.get("no_findings", False)),
                metadata=arguments.get("metadata") or {},
                provider=arguments.get("provider"),
            )
            return {"success": True, "result": review.model_dump(mode="json"), "metadata": {"request_mode": "architecture_review_submit", "review_id": review.review_id, "direct_registry_mutation": False}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_review_submit"}, "error": str(exc)}

    def architecture_review_get(arguments: dict[str, Any]) -> dict[str, Any]:
        review_id = str(arguments.get("review_id") or "")
        if not review_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "review_id_required"}
        try:
            review = service().get_review(review_id)
            return {"success": True, "result": review.model_dump(mode="json"), "metadata": {"request_mode": "architecture_review_get", "review_id": review_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_review_get"}, "error": str(exc)}

    def architecture_review_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().list_reviews(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            limit=int(arguments.get("limit") or 50),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_review_list"}, "error": None}

    def architecture_finding_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            finding = service().submit_finding(
                project_id=str(arguments.get("project_id") or ""),
                created_by=str(arguments.get("agent_id") or arguments.get("created_by") or ""),
                summary=str(arguments.get("summary") or ""),
                affected_architecture_ids=arguments.get("affected_architecture_ids") or ([arguments.get("architecture_id") or arguments.get("path")] if (arguments.get("architecture_id") or arguments.get("path")) else []),
                review_id=arguments.get("review_id"),
                severity=str(arguments.get("severity") or "concern"),
                category=str(arguments.get("category") or "other"),
                rationale=str(arguments.get("rationale") or ""),
                other_explanation=str(arguments.get("other_explanation") or ""),
                metadata=arguments.get("metadata") or {},
                provider=arguments.get("provider"),
            )
            return {"success": True, "result": finding.model_dump(mode="json"), "metadata": {"request_mode": "architecture_finding_submit", "finding_id": finding.finding_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_finding_submit"}, "error": str(exc)}

    def architecture_challenge_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        try:
            challenge = service().submit_challenge(
                project_id=str(arguments.get("project_id") or ""),
                architecture_id_or_path=identifier,
                submitted_by=str(arguments.get("agent_id") or arguments.get("submitted_by") or ""),
                challenge_summary=str(arguments.get("challenge_summary") or arguments.get("summary") or ""),
                context=str(arguments.get("context") or ""),
                intent=str(arguments.get("intent") or ""),
                finding_id=arguments.get("finding_id"),
                rationale=str(arguments.get("rationale") or ""),
                proposed_direction=str(arguments.get("proposed_direction") or ""),
                metadata=arguments.get("metadata") or {},
                provider=arguments.get("provider"),
            )
            return {"success": True, "result": challenge.model_dump(mode="json"), "metadata": {"request_mode": "architecture_challenge_submit", "challenge_id": challenge.challenge_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_challenge_submit"}, "error": str(exc)}

    def architecture_challenge_get(arguments: dict[str, Any]) -> dict[str, Any]:
        challenge_id = str(arguments.get("challenge_id") or "")
        if not challenge_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "challenge_id_required"}
        try:
            challenge = service().get_challenge(challenge_id)
            return {"success": True, "result": challenge.model_dump(mode="json"), "metadata": {"request_mode": "architecture_challenge_get", "challenge_id": challenge_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_challenge_get"}, "error": str(exc)}

    def architecture_challenge_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().list_challenges(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            limit=int(arguments.get("limit") or 50),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_challenge_list"}, "error": None}

    def architecture_revision_propose(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        try:
            revision = service().propose_revision(
                project_id=str(arguments.get("project_id") or ""),
                architecture_id_or_path=identifier,
                submitted_by=str(arguments.get("agent_id") or arguments.get("submitted_by") or ""),
                objective=str(arguments.get("objective") or ""),
                proposed_changes=arguments.get("proposed_changes") or {},
                challenge_id=arguments.get("challenge_id"),
                metadata={"session_id": arguments.get("session_id"), **dict(arguments.get("metadata") or {})},
                provider=arguments.get("provider"),
            )
            return {"success": True, "result": revision.model_dump(mode="json"), "metadata": {"request_mode": "architecture_revision_propose", "revision_id": revision.revision_id, "linked_proposal_id": revision.linked_proposal_id, "direct_registry_mutation": False}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_revision_propose"}, "error": str(exc)}

    def architecture_revisions(arguments: dict[str, Any]) -> dict[str, Any]:
        result = revision_service().list_revisions(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            limit=int(arguments.get("limit") or 50),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_revisions"}, "error": None}

    def architecture_revision_details(arguments: dict[str, Any]) -> dict[str, Any]:
        revision_id = str(arguments.get("revision_id") or "")
        if not revision_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "revision_id_required"}
        try:
            result = revision_service().get_revision(revision_id, include_snapshot=bool(arguments.get("include_snapshot", False)))
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_revision_details", "revision_id": revision_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_revision_details"}, "error": str(exc)}

    def architecture_history(arguments: dict[str, Any]) -> dict[str, Any]:
        architecture_id = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if arguments.get("path") and not str(arguments.get("architecture_id") or ""):
            try:
                architecture_id = service().require_node(str(arguments.get("path"))).architecture_id
            except Exception as exc:
                return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_history"}, "error": str(exc)}
        if not architecture_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        result = revision_service().get_history(
            architecture_id=architecture_id,
            project_id=str(arguments.get("project_id") or "") or None,
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_history", "architecture_id": architecture_id}, "error": None}

    def architecture_baseline_current(arguments: dict[str, Any]) -> dict[str, Any]:
        architecture_id = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if arguments.get("path") and not str(arguments.get("architecture_id") or ""):
            try:
                architecture_id = service().require_node(str(arguments.get("path"))).architecture_id
            except Exception as exc:
                return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_baseline_current"}, "error": str(exc)}
        if not architecture_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        try:
            result = revision_service().current_baseline_details(
                architecture_id=architecture_id,
                project_id=str(arguments.get("project_id") or "") or None,
                include_snapshot=bool(arguments.get("include_snapshot", True)),
            )
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_baseline_current", "architecture_id": architecture_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_baseline_current"}, "error": str(exc)}


    def architecture_adr_propose(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            adr = adr_service().propose_adr(
                project_id=str(arguments.get("project_id") or ""),
                session_id=str(arguments.get("session_id") or "architecture-adr"),
                created_by=str(arguments.get("agent_id") or arguments.get("created_by") or ""),
                title=str(arguments.get("title") or ""),
                context=str(arguments.get("context") or ""),
                decision=str(arguments.get("decision") or ""),
                rationale=str(arguments.get("rationale") or ""),
                alternatives_considered=arguments.get("alternatives_considered") or [],
                consequences=arguments.get("consequences") or [],
                tradeoffs=arguments.get("tradeoffs") or [],
                future_considerations=arguments.get("future_considerations") or [],
                architecture_ids=arguments.get("architecture_ids") or ([arguments.get("architecture_id")] if arguments.get("architecture_id") else []),
                revision_ids=arguments.get("revision_ids") or ([arguments.get("revision_id")] if arguments.get("revision_id") else []),
                related_adr_ids=arguments.get("related_adr_ids") or [],
                supersedes_adr_id=arguments.get("supersedes_adr_id"),
                evidence_package_ids=arguments.get("evidence_package_ids") or [],
                metadata={"session_id": arguments.get("session_id"), **dict(arguments.get("metadata") or {})},
            )
            return {"success": True, "result": adr.model_dump(mode="json"), "metadata": {"request_mode": "architecture_adr_propose", "adr_id": adr.adr_id, "proposal_id": adr.proposal_id, "direct_adr_acceptance": False}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_adr_propose"}, "error": str(exc)}

    def architecture_adrs(arguments: dict[str, Any]) -> dict[str, Any]:
        result = adr_service().list_adrs(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            revision_id=str(arguments.get("revision_id") or "") or None,
            status=str(arguments.get("status") or "") or None,
            limit=int(arguments.get("limit") or 50),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_adrs"}, "error": None}

    def architecture_adr_details(arguments: dict[str, Any]) -> dict[str, Any]:
        adr_id = str(arguments.get("adr_id") or "")
        if not adr_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "adr_id_required"}
        try:
            result = adr_service().get_adr(adr_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_adr_details", "adr_id": adr_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_adr_details"}, "error": str(exc)}

    def architecture_adr_history(arguments: dict[str, Any]) -> dict[str, Any]:
        adr_id = str(arguments.get("adr_id") or "")
        if not adr_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "adr_id_required"}
        try:
            result = adr_service().get_history(adr_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_adr_history", "adr_id": adr_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_adr_history"}, "error": str(exc)}


    def architecture_principle_propose(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            principle = guidance_service().propose_principle(
                project_id=str(arguments.get("project_id") or ""),
                session_id=str(arguments.get("session_id") or "architecture-principle"),
                created_by=str(arguments.get("agent_id") or arguments.get("created_by") or ""),
                title=str(arguments.get("title") or ""),
                statement=str(arguments.get("statement") or ""),
                rationale=str(arguments.get("rationale") or ""),
                scope=str(arguments.get("scope") or "project"),
                architecture_ids=arguments.get("architecture_ids") or ([arguments.get("architecture_id")] if arguments.get("architecture_id") else []),
                adr_ids=arguments.get("adr_ids") or ([arguments.get("adr_id")] if arguments.get("adr_id") else []),
                revision_ids=arguments.get("revision_ids") or ([arguments.get("revision_id")] if arguments.get("revision_id") else []),
                related_principle_ids=arguments.get("related_principle_ids") or [],
                supersedes_principle_id=arguments.get("supersedes_principle_id"),
                evidence_package_ids=arguments.get("evidence_package_ids") or [],
                metadata={"session_id": arguments.get("session_id"), **dict(arguments.get("metadata") or {})},
            )
            return {"success": True, "result": principle.model_dump(mode="json"), "metadata": {"request_mode": "architecture_principle_propose", "principle_id": principle.principle_id, "proposal_id": principle.proposal_id, "direct_principle_acceptance": False}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_principle_propose"}, "error": str(exc)}

    def architecture_principles(arguments: dict[str, Any]) -> dict[str, Any]:
        result = guidance_service().list_principles(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            adr_id=str(arguments.get("adr_id") or "") or None,
            revision_id=str(arguments.get("revision_id") or "") or None,
            status=str(arguments.get("status") or "") or None,
            limit=int(arguments.get("limit") or 50),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_principles"}, "error": None}

    def architecture_principle_details(arguments: dict[str, Any]) -> dict[str, Any]:
        principle_id = str(arguments.get("principle_id") or "")
        if not principle_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "principle_id_required"}
        try:
            result = guidance_service().get_principle(principle_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_principle_details", "principle_id": principle_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_principle_details"}, "error": str(exc)}

    def architecture_principle_history(arguments: dict[str, Any]) -> dict[str, Any]:
        principle_id = str(arguments.get("principle_id") or "")
        if not principle_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "principle_id_required"}
        try:
            result = guidance_service().get_principle_history(principle_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_principle_history", "principle_id": principle_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_principle_history"}, "error": str(exc)}

    def architecture_intent_propose(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            intent = guidance_service().propose_intent(
                project_id=str(arguments.get("project_id") or ""),
                session_id=str(arguments.get("session_id") or "architecture-intent"),
                created_by=str(arguments.get("agent_id") or arguments.get("created_by") or ""),
                title=str(arguments.get("title") or ""),
                summary=str(arguments.get("summary") or ""),
                details=str(arguments.get("details") or ""),
                scope=str(arguments.get("scope") or "project"),
                future_considerations=arguments.get("future_considerations") or [],
                architecture_ids=arguments.get("architecture_ids") or ([arguments.get("architecture_id")] if arguments.get("architecture_id") else []),
                adr_ids=arguments.get("adr_ids") or ([arguments.get("adr_id")] if arguments.get("adr_id") else []),
                principle_ids=arguments.get("principle_ids") or ([arguments.get("principle_id")] if arguments.get("principle_id") else []),
                revision_ids=arguments.get("revision_ids") or ([arguments.get("revision_id")] if arguments.get("revision_id") else []),
                related_intent_ids=arguments.get("related_intent_ids") or [],
                supersedes_intent_id=arguments.get("supersedes_intent_id"),
                evidence_package_ids=arguments.get("evidence_package_ids") or [],
                metadata={"session_id": arguments.get("session_id"), **dict(arguments.get("metadata") or {})},
            )
            return {"success": True, "result": intent.model_dump(mode="json"), "metadata": {"request_mode": "architecture_intent_propose", "intent_id": intent.intent_id, "proposal_id": intent.proposal_id, "direct_intent_acceptance": False}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_intent_propose"}, "error": str(exc)}

    def architecture_intents(arguments: dict[str, Any]) -> dict[str, Any]:
        result = guidance_service().list_intents(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            adr_id=str(arguments.get("adr_id") or "") or None,
            principle_id=str(arguments.get("principle_id") or "") or None,
            revision_id=str(arguments.get("revision_id") or "") or None,
            status=str(arguments.get("status") or "") or None,
            limit=int(arguments.get("limit") or 50),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_intents"}, "error": None}

    def architecture_intent_details(arguments: dict[str, Any]) -> dict[str, Any]:
        intent_id = str(arguments.get("intent_id") or "")
        if not intent_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "intent_id_required"}
        try:
            result = guidance_service().get_intent(intent_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_intent_details", "intent_id": intent_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_intent_details"}, "error": str(exc)}

    def architecture_intent_history(arguments: dict[str, Any]) -> dict[str, Any]:
        intent_id = str(arguments.get("intent_id") or "")
        if not intent_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "intent_id_required"}
        try:
            result = guidance_service().get_intent_history(intent_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_intent_history", "intent_id": intent_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_intent_history"}, "error": str(exc)}

    def architecture_guidance(arguments: dict[str, Any]) -> dict[str, Any]:
        result = guidance_service().get_guidance(
            project_id=str(arguments.get("project_id") or "") or None,
            architecture_id=str(arguments.get("architecture_id") or "") or None,
            adr_id=str(arguments.get("adr_id") or "") or None,
            revision_id=str(arguments.get("revision_id") or "") or None,
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_guidance", "derived_guidance": True}, "error": None}


    def architecture_guidance_context(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            package = guidance_context_service().build_context_package(
                project_id=str(arguments.get("project_id") or "") or None,
                architecture_id=str(arguments.get("architecture_id") or "") or None,
                path=str(arguments.get("path") or "") or None,
                adr_id=str(arguments.get("adr_id") or "") or None,
                revision_id=str(arguments.get("revision_id") or "") or None,
                principle_id=str(arguments.get("principle_id") or "") or None,
                intent_id=str(arguments.get("intent_id") or "") or None,
                persist=bool(arguments.get("persist", False)),
                created_by=str(arguments.get("agent_id") or "architecture_guidance_context_service"),
            )
            return {"success": True, "result": package.model_dump(mode="json"), "metadata": {"request_mode": "architecture_guidance_context", "package_id": package.package_id, "persisted_snapshot": package.persisted_snapshot}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_guidance_context"}, "error": str(exc)}

    def architecture_guidance_context_get(arguments: dict[str, Any]) -> dict[str, Any]:
        package_id = str(arguments.get("package_id") or "")
        if not package_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "package_id_required"}
        try:
            result = guidance_context_service().get_package(package_id)
            return {"success": True, "result": result, "metadata": {"request_mode": "architecture_guidance_context_get", "package_id": package_id}, "error": None}
        except Exception as exc:
            return {"success": False, "result": {}, "metadata": {"request_mode": "architecture_guidance_context_get"}, "error": str(exc)}

    def architecture_seed_ageix(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().seed_official_ageix_architecture()
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_seed_ageix"}, "error": None}

    return [
        (CapabilityDefinition(capability_id="architecture.list", category="architecture", access_level="governed_read", handler="architecture.list", description="List project-scoped architecture hierarchy nodes."), architecture_list),
        (CapabilityDefinition(capability_id="architecture.details", category="architecture", access_level="governed_read", handler="architecture.details", description="Retrieve one architecture node by architecture ID or path."), architecture_details),
        (CapabilityDefinition(capability_id="architecture.children", category="architecture", access_level="governed_read", handler="architecture.children", description="Retrieve direct children for an architecture node."), architecture_children),
        (CapabilityDefinition(capability_id="architecture.subtree", category="architecture", access_level="governed_read", handler="architecture.subtree", description="Retrieve an architecture hierarchy subtree."), architecture_subtree),
        (CapabilityDefinition(capability_id="architecture.context", category="architecture", access_level="governed_read", handler="architecture.context", description="Build summary-first architecture context for a node without repository-wide discovery."), architecture_context),
        (CapabilityDefinition(capability_id="architecture.health", category="architecture", access_level="governed_read", handler="architecture.health", description="Return deterministic architecture health indicators for one architecture node."), architecture_health),
        (CapabilityDefinition(capability_id="architecture.coverage", category="architecture", access_level="governed_read", handler="architecture.coverage", description="Return deterministic architecture coverage metrics for a project registry baseline."), architecture_coverage),
        (CapabilityDefinition(capability_id="architecture.baseline.validate", category="architecture", access_level="governed_read", handler="architecture.baseline.validate", description="Validate the official architecture baseline using registry and health data."), architecture_baseline_validate),
        (CapabilityDefinition(capability_id="architecture.review.submit", category="architecture", access_level="governed_write", handler="architecture.review.submit", description="Submit a governed architecture review from an authorized architect MCP partner."), architecture_review_submit),
        (CapabilityDefinition(capability_id="architecture.review.get", category="architecture", access_level="governed_read", handler="architecture.review.get", description="Retrieve a governed architecture review."), architecture_review_get),
        (CapabilityDefinition(capability_id="architecture.review.list", category="architecture", access_level="governed_read", handler="architecture.review.list", description="List governed architecture reviews."), architecture_review_list),
        (CapabilityDefinition(capability_id="architecture.finding.submit", category="architecture", access_level="governed_write", handler="architecture.finding.submit", description="Submit a structured architecture review finding from an authorized architect MCP partner."), architecture_finding_submit),
        (CapabilityDefinition(capability_id="architecture.challenge.submit", category="architecture", access_level="governed_write", handler="architecture.challenge.submit", description="Submit an architecture challenge with context and intent."), architecture_challenge_submit),
        (CapabilityDefinition(capability_id="architecture.challenge.get", category="architecture", access_level="governed_read", handler="architecture.challenge.get", description="Retrieve a governed architecture challenge."), architecture_challenge_get),
        (CapabilityDefinition(capability_id="architecture.challenge.list", category="architecture", access_level="governed_read", handler="architecture.challenge.list", description="List governed architecture challenges."), architecture_challenge_list),
        (CapabilityDefinition(capability_id="architecture.revision.propose", category="architecture", access_level="governed_write", handler="architecture.revision.propose", description="Propose a governed architecture registry revision through the existing proposal system."), architecture_revision_propose),
        (CapabilityDefinition(capability_id="architecture.revisions", category="architecture", access_level="governed_read", handler="architecture.revisions", description="List immutable governed architecture revisions."), architecture_revisions),
        (CapabilityDefinition(capability_id="architecture.revision.details", category="architecture", access_level="governed_read", handler="architecture.revision.details", description="Retrieve immutable architecture revision details, optionally including the snapshot."), architecture_revision_details),
        (CapabilityDefinition(capability_id="architecture.history", category="architecture", access_level="governed_read", handler="architecture.history", description="Retrieve architecture revision history and current authoritative baseline."), architecture_history),
        (CapabilityDefinition(capability_id="architecture.baseline.current", category="architecture", access_level="governed_read", handler="architecture.baseline.current", description="Retrieve the current authoritative architecture baseline."), architecture_baseline_current),
        (CapabilityDefinition(capability_id="architecture.adr.propose", category="architecture", access_level="governed_write", handler="architecture.adr.propose", description="Propose a governed Architecture Decision Record through the existing proposal system."), architecture_adr_propose),
        (CapabilityDefinition(capability_id="architecture.adrs", category="architecture", access_level="governed_read", handler="architecture.adrs", description="List governed Architecture Decision Records."), architecture_adrs),
        (CapabilityDefinition(capability_id="architecture.adr.details", category="architecture", access_level="governed_read", handler="architecture.adr.details", description="Retrieve Architecture Decision Record details."), architecture_adr_details),
        (CapabilityDefinition(capability_id="architecture.adr.history", category="architecture", access_level="governed_read", handler="architecture.adr.history", description="Retrieve Architecture Decision Record supersession history."), architecture_adr_history),
        (CapabilityDefinition(capability_id="architecture.principle.propose", category="architecture", access_level="governed_write", handler="architecture.principle.propose", description="Propose a governed Architecture Principle through the existing proposal system."), architecture_principle_propose),
        (CapabilityDefinition(capability_id="architecture.principles", category="architecture", access_level="governed_read", handler="architecture.principles", description="List governed Architecture Principles."), architecture_principles),
        (CapabilityDefinition(capability_id="architecture.principle.details", category="architecture", access_level="governed_read", handler="architecture.principle.details", description="Retrieve Architecture Principle details."), architecture_principle_details),
        (CapabilityDefinition(capability_id="architecture.principle.history", category="architecture", access_level="governed_read", handler="architecture.principle.history", description="Retrieve Architecture Principle supersession history."), architecture_principle_history),
        (CapabilityDefinition(capability_id="architecture.intent.propose", category="architecture", access_level="governed_write", handler="architecture.intent.propose", description="Propose governed Architecture Intent through the existing proposal system."), architecture_intent_propose),
        (CapabilityDefinition(capability_id="architecture.intents", category="architecture", access_level="governed_read", handler="architecture.intents", description="List governed Architecture Intent records."), architecture_intents),
        (CapabilityDefinition(capability_id="architecture.intent.details", category="architecture", access_level="governed_read", handler="architecture.intent.details", description="Retrieve Architecture Intent details."), architecture_intent_details),
        (CapabilityDefinition(capability_id="architecture.intent.history", category="architecture", access_level="governed_read", handler="architecture.intent.history", description="Retrieve Architecture Intent supersession history."), architecture_intent_history),
        (CapabilityDefinition(capability_id="architecture.guidance", category="architecture", access_level="governed_read", handler="architecture.guidance", description="Return derived architecture guidance from accepted principles and intent."), architecture_guidance),
        (CapabilityDefinition(capability_id="architecture.guidance.context", category="architecture", access_level="governed_read", handler="architecture.guidance.context", description="Build or persist a summary-first Architecture Guidance Context Package."), architecture_guidance_context),
        (CapabilityDefinition(capability_id="architecture.guidance.context.get", category="architecture", access_level="governed_read", handler="architecture.guidance.context.get", description="Retrieve a persisted Architecture Guidance Context Package."), architecture_guidance_context_get),
        (CapabilityDefinition(capability_id="architecture.description.draft", category="architecture", access_level="governed_write", handler="architecture.description.draft", description="Create an ArchitectWorker draft architecture description artifact.", exposed_to_external_agents=False), architecture_description_draft),
        (CapabilityDefinition(capability_id="architecture.description.approve", category="architecture", access_level="governed_write", handler="architecture.description.approve", description="Chair approval for an architecture description artifact.", exposed_to_external_agents=False), architecture_description_approve),
        (CapabilityDefinition(capability_id="architecture.seed_ageix", category="architecture", access_level="governed_write", handler="architecture.seed_ageix", description="Seed the official Ageix project architecture baseline.", exposed_to_external_agents=False), architecture_seed_ageix),
    ]
