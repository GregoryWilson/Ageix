from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.architecture_context_service import ArchitectureContextService
from services.architecture_registry_service import ArchitectureRegistryService


def register_capabilities(repo_root: Path):
    def service() -> ArchitectureRegistryService:
        return ArchitectureRegistryService(repo_root)

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
        (CapabilityDefinition(capability_id="architecture.review.submit", category="architecture", access_level="governed_write", handler="architecture.review.submit", description="Submit a governed architecture review from an authorized architect MCP partner."), architecture_review_submit),
        (CapabilityDefinition(capability_id="architecture.review.get", category="architecture", access_level="governed_read", handler="architecture.review.get", description="Retrieve a governed architecture review."), architecture_review_get),
        (CapabilityDefinition(capability_id="architecture.review.list", category="architecture", access_level="governed_read", handler="architecture.review.list", description="List governed architecture reviews."), architecture_review_list),
        (CapabilityDefinition(capability_id="architecture.finding.submit", category="architecture", access_level="governed_write", handler="architecture.finding.submit", description="Submit a structured architecture review finding from an authorized architect MCP partner."), architecture_finding_submit),
        (CapabilityDefinition(capability_id="architecture.challenge.submit", category="architecture", access_level="governed_write", handler="architecture.challenge.submit", description="Submit an architecture challenge with context and intent."), architecture_challenge_submit),
        (CapabilityDefinition(capability_id="architecture.challenge.get", category="architecture", access_level="governed_read", handler="architecture.challenge.get", description="Retrieve a governed architecture challenge."), architecture_challenge_get),
        (CapabilityDefinition(capability_id="architecture.challenge.list", category="architecture", access_level="governed_read", handler="architecture.challenge.list", description="List governed architecture challenges."), architecture_challenge_list),
        (CapabilityDefinition(capability_id="architecture.revision.propose", category="architecture", access_level="governed_write", handler="architecture.revision.propose", description="Propose a governed architecture registry revision through the existing proposal system."), architecture_revision_propose),
        (CapabilityDefinition(capability_id="architecture.description.draft", category="architecture", access_level="governed_write", handler="architecture.description.draft", description="Create an ArchitectWorker draft architecture description artifact.", exposed_to_external_agents=False), architecture_description_draft),
        (CapabilityDefinition(capability_id="architecture.description.approve", category="architecture", access_level="governed_write", handler="architecture.description.approve", description="Chair approval for an architecture description artifact.", exposed_to_external_agents=False), architecture_description_approve),
        (CapabilityDefinition(capability_id="architecture.seed_ageix", category="architecture", access_level="governed_write", handler="architecture.seed_ageix", description="Seed the official Ageix project architecture baseline.", exposed_to_external_agents=False), architecture_seed_ageix),
    ]
