from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.agent_profile_service import AgentProfileService


def _safe_profile(profile) -> dict[str, Any]:
    return {
        "agent_id": profile.agent_id,
        "display_name": profile.display_name,
        "reputation_level": profile.reputation_level,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "notes": profile.notes,
    }


def register_capabilities(repo_root: Path):
    def agent_list(arguments: dict[str, Any]) -> dict[str, Any]:
        profiles = [_safe_profile(profile) for profile in AgentProfileService(repo_root).list_profiles()]
        return {"success": True, "result": {"agents": profiles}, "metadata": {"source": "agent_profiles"}}

    def agent_profile(arguments: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(arguments.get("profile_agent_id") or arguments.get("agent_profile_id") or arguments.get("agent_id") or "")
        if not agent_id:
            return {"success": False, "result": {}, "error": "agent_id_required"}
        profile = AgentProfileService(repo_root).get_profile(agent_id)
        return {"success": True, "result": _safe_profile(profile), "metadata": {"source": "agent_profiles"}}

    return [
        (CapabilityDefinition(
            capability_id="agent.list",
            category="agent",
            access_level="read",
            handler="agent.list",
            description="List human-managed external agent profiles and reputation levels.",
        ), agent_list),
        (CapabilityDefinition(
            capability_id="agent.profile",
            category="agent",
            access_level="read",
            handler="agent.profile",
            description="Return a human-managed external agent reputation profile.",
        ), agent_profile),
    ]
