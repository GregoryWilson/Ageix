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
    ]
