from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.validation_operations_service import ValidationOperationsService


def register_capabilities(repo_root: Path):
    def service() -> ValidationOperationsService:
        return ValidationOperationsService(repo_root)

    def ok(result: dict[str, Any], mode: str) -> dict[str, Any]:
        return {"success": True, "result": result, "metadata": {"request_mode": mode, "repository_target": str(repo_root)}, "error": None}

    def profile_list(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().list_profiles(limit=int(arguments.get("limit") or 50), offset=int(arguments.get("offset") or 0)), "validation_profile_list")

    def profile_get(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().get_profile(str(arguments.get("profile_id") or "")), "validation_profile_get")

    def run_start(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().start_run(profile_id=str(arguments.get("profile_id") or ""), agent_id=arguments.get("agent_id"), session_id=arguments.get("session_id")), "validation_run_start")

    def run_status(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().status(str(arguments.get("run_id") or "")), "validation_run_status")

    def run_result(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().result(str(arguments.get("run_id") or "")), "validation_run_result")

    def history(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().history(limit=int(arguments.get("limit") or 10), offset=int(arguments.get("offset") or 0)), "validation_history")

    return [
        (CapabilityDefinition(capability_id="validation.profile.list", category="validation", access_level="governed_read", handler="validation.profile.list", description="List approved validation profiles."), profile_list),
        (CapabilityDefinition(capability_id="validation.profile.get", category="validation", access_level="governed_read", handler="validation.profile.get", description="Get an approved validation profile by ID."), profile_get),
        (CapabilityDefinition(capability_id="validation.run.start", category="validation", access_level="governed_execute", handler="validation.run.start", description="Start a registered validation profile asynchronously."), run_start),
        (CapabilityDefinition(capability_id="validation.run.status", category="validation", access_level="governed_read", handler="validation.run.status", description="Return status for a validation run."), run_status),
        (CapabilityDefinition(capability_id="validation.run.result", category="validation", access_level="governed_read", handler="validation.run.result", description="Return summary-first validation run result and output tails."), run_result),
        (CapabilityDefinition(capability_id="validation.history", category="validation", access_level="governed_read", handler="validation.history", description="List validation run history."), history),
    ]
