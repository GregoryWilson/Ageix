from __future__ import annotations

from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_definition import CapabilityDefinition
from services.devjob_registry_service import DevJobRegistryService


def register_capabilities(repo_root: Path):
    def registry() -> DevJobRegistryService:
        return DevJobRegistryService(repo_root)

    def _actor_id(arguments: dict[str, Any]) -> str:
        return str(arguments.get("actor_id") or arguments.get("client_id") or "")

    def devjob_create(arguments: dict[str, Any]) -> dict[str, Any]:
        title = str(arguments.get("title") or "")
        objective = str(arguments.get("objective") or "")
        if not title:
            return {"success": False, "result": {}, "error": "title_required"}
        if not objective:
            return {"success": False, "result": {}, "error": "objective_required"}
        created_by = str(arguments.get("created_by") or _actor_id(arguments))
        try:
            job = registry().create_job(
                title=title,
                objective=objective,
                instructions=arguments.get("instructions") or [],
                acceptance_criteria=arguments.get("acceptance_criteria") or [],
                allowed_paths=arguments.get("allowed_paths") or [],
                prohibited_paths=arguments.get("prohibited_paths") or [],
                repo_target=arguments.get("repo_target"),
                branch_hint=arguments.get("branch_hint"),
                evidence_package_ids=arguments.get("evidence_package_ids") or [],
                work_context_id=arguments.get("work_context_id"),
                validation_profile_ids=arguments.get("validation_profile_ids") or [],
                conversation_id=arguments.get("conversation_id"),
                handoff_id=arguments.get("handoff_id"),
                origin=str(arguments.get("origin") or "manual"),
                status=str(arguments.get("status") or "draft"),
                created_by=created_by,
                assigned_to=arguments.get("assigned_to"),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_list(arguments: dict[str, Any]) -> dict[str, Any]:
        raw_limit = arguments.get("limit")
        result = registry().list_jobs(
            status=arguments.get("status"),
            assigned_to=arguments.get("assigned_to"),
            created_by=arguments.get("created_by"),
            repo_target=arguments.get("repo_target"),
            limit=int(raw_limit) if raw_limit is not None else 20,
            offset=int(arguments.get("offset") or 0),
        )
        return {"success": True, "result": result, "metadata": {"source": "devjob_registry_service"}}

    def devjob_get(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        try:
            job = registry().get_job(job_id)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_result_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        submitted_by = str(arguments.get("submitted_by") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            result = registry().submit_result(
                job_id=job_id,
                result_summary=str(arguments.get("result_summary") or ""),
                status=str(arguments.get("status") or "success"),
                public_branch_or_pr=arguments.get("public_branch_or_pr"),
                branch_name=arguments.get("branch_name"),
                changed_files=arguments.get("changed_files") or [],
                patch_id=arguments.get("patch_id"),
                artifact_ids=arguments.get("artifact_ids") or [],
                validation_run_id=arguments.get("validation_run_id"),
                validation_notes=str(arguments.get("validation_notes") or ""),
                submitted_by=submitted_by,
                actor_role=actor_role,
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": result, "metadata": {"source": "devjob_registry_service"}}

    def devjob_assign(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        actor_id = str(arguments.get("actor_id") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            job = registry().assign_job(
                job_id,
                work_context_id=arguments.get("work_context_id"),
                acceptance_criteria=arguments.get("acceptance_criteria"),
                allowed_paths=arguments.get("allowed_paths"),
                prohibited_paths=arguments.get("prohibited_paths"),
                instructions=arguments.get("instructions"),
                assigned_to=arguments.get("assigned_to"),
                actor_id=actor_id,
                actor_role=actor_role,
                note=str(arguments.get("note") or ""),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_transition(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        target_status = str(arguments.get("target_status") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        if not target_status:
            return {"success": False, "result": {}, "error": "target_status_required"}
        actor_id = str(arguments.get("actor_id") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            job = registry().transition_job(
                job_id,
                target_status,  # type: ignore[arg-type]
                actor_id=actor_id,
                actor_role=actor_role,
                note=str(arguments.get("note") or ""),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_event_list(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        try:
            result = registry().list_events(job_id)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": result, "metadata": {"source": "devjob_registry_service"}}

    def devjob_review_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        actor_id = str(arguments.get("actor_id") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            job = registry().submit_review(
                job_id,
                decision=str(arguments.get("decision") or ""),
                reviewer_notes=str(arguments.get("reviewer_notes") or ""),
                actor_id=actor_id,
                actor_role=actor_role,
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_sync_attach(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        actor_id = str(arguments.get("actor_id") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            job = registry().attach_sync(
                job_id,
                branch=arguments.get("branch"),
                pr_reference=arguments.get("pr_reference"),
                commit_sha=arguments.get("commit_sha"),
                note=str(arguments.get("note") or ""),
                actor_id=actor_id,
                actor_role=actor_role,
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_scope_revise(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        actor_id = str(arguments.get("actor_id") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            job = registry().revise_scope(
                job_id,
                reason=str(arguments.get("reason") or ""),
                evidence_package_ids=arguments.get("evidence_package_ids") or [],
                instructions=arguments.get("instructions"),
                acceptance_criteria=arguments.get("acceptance_criteria"),
                allowed_paths=arguments.get("allowed_paths"),
                prohibited_paths=arguments.get("prohibited_paths"),
                actor_id=actor_id,
                actor_role=actor_role,
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    def devjob_validation_waiver(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if not job_id:
            return {"success": False, "result": {}, "error": "job_id_required"}
        actor_id = str(arguments.get("actor_id") or _actor_id(arguments))
        actor_role = AgentRole.parse(str(arguments.get("agent_role") or ""))
        try:
            job = registry().record_validation_waiver(
                job_id,
                reason=str(arguments.get("reason") or ""),
                actor_id=actor_id,
                actor_role=actor_role,
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": job.to_metadata(), "metadata": {"source": "devjob_registry_service"}}

    return [
        (CapabilityDefinition(
            capability_id="devjob.create",
            category="devjob",
            access_level="governed_read",
            handler="devjob.create",
            description="Create a governed DevJob work assignment describing what should be implemented, reviewed, or investigated, per INTENT-0007. Does not execute work.",
        ), devjob_create),
        (CapabilityDefinition(
            capability_id="devjob.list",
            category="devjob",
            access_level="governed_read",
            handler="devjob.list",
            description="List DevJob work assignments with optional status, assignee, creator, and repo target filters.",
        ), devjob_list),
        (CapabilityDefinition(
            capability_id="devjob.get",
            category="devjob",
            access_level="governed_read",
            handler="devjob.get",
            description="Retrieve a DevJob work assignment by ID, including its lifecycle history.",
        ), devjob_get),
        (CapabilityDefinition(
            capability_id="devjob.result.submit",
            category="devjob",
            access_level="governed_read",
            handler="devjob.result.submit",
            description="Submit a reference-only DevJob result (patch_id, artifact_ids, validation_run_id, branch info) and move the DevJob to submitted, per INTENT-0007.",
        ), devjob_result_submit),
        (CapabilityDefinition(
            capability_id="devjob.assign",
            category="devjob",
            access_level="governed_read",
            handler="devjob.assign",
            description="Move a draft DevJob to assigned, requiring a resolvable WORKCTX-*, acceptance criteria, allowed/prohibited paths, an assigned worker, and an authorized assigner, per INTENT-0007 Phase 2.",
        ), devjob_assign),
        (CapabilityDefinition(
            capability_id="devjob.transition",
            category="devjob",
            access_level="governed_read",
            handler="devjob.transition",
            description="Move a DevJob to an allowed lifecycle status (in_progress, blocked, declined, reviewed, completed, cancelled), enforcing authorization, reason requirements, and the completion gate, per INTENT-0007 Phase 2.",
        ), devjob_transition),
        (CapabilityDefinition(
            capability_id="devjob.event.list",
            category="devjob",
            access_level="governed_read",
            handler="devjob.event.list",
            description="List a DevJob's full governed event history: lifecycle transitions plus non-status events (scope_revision, validation_waiver, git_sync_attached, review_submitted), in chronological order.",
        ), devjob_event_list),
        (CapabilityDefinition(
            capability_id="devjob.review.submit",
            category="devjob",
            access_level="governed_read",
            handler="devjob.review.submit",
            description="Submit a formal review decision (approved or changes_requested) for a submitted DevJob, moving it to reviewed or declined, per INTENT-0007 Phase 2.",
        ), devjob_review_submit),
        (CapabilityDefinition(
            capability_id="devjob.sync.attach",
            category="devjob",
            access_level="governed_read",
            handler="devjob.sync.attach",
            description="Record a git synchronization reference (branch, PR, or commit SHA) on a DevJob by reference only; never mutates the target repository, per INTENT-0007 Phase 2.",
        ), devjob_sync_attach),
        (CapabilityDefinition(
            capability_id="devjob.scope.revise",
            category="devjob",
            access_level="governed_read",
            handler="devjob.scope.revise",
            description="Record an evidence-gated revision to a DevJob's scope (instructions, acceptance criteria, allowed/prohibited paths) as an append-only event rather than an in-place edit, per INTENT-0007 Phase 2.",
        ), devjob_scope_revise),
        (CapabilityDefinition(
            capability_id="devjob.validation.waiver",
            category="devjob",
            access_level="governed_read",
            handler="devjob.validation.waiver",
            description="Record a governed waiver of the validation-attached completion requirement for a DevJob; restricted to Greg/governance and requires a reason, per INTENT-0007 Phase 2.",
        ), devjob_validation_waiver),
    ]
