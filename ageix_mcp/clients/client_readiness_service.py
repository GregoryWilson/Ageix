from __future__ import annotations

from typing import Any


class ClientReadinessService:
    """Produces objective MCP client readiness metadata from validation evidence."""

    REQUIRED_CATEGORIES = {"proposal", "consultation", "project", "workflow", "identity", "audit"}

    def assess(self, *, client_id: str, validation: dict[str, Any]) -> dict[str, object]:
        discovered_categories = set(validation.get("discovered_categories") or [])
        discovery_ready = self.REQUIRED_CATEGORIES.issubset(discovered_categories) and bool(validation.get("schema_consumed"))
        workflow_ready = bool(validation.get("workflow_navigation_succeeded")) and bool(validation.get("workflow_hints_consumed"))
        session_ready = bool(validation.get("session_continuity_succeeded"))
        identity_ready = bool(validation.get("identity_continuity_succeeded"))
        governance_ready = bool(validation.get("governance_denials_succeeded"))
        audit_ready = bool(validation.get("audit_continuity_succeeded"))
        return {
            "client_id": client_id,
            "discovery_ready": discovery_ready,
            "workflow_ready": workflow_ready,
            "session_ready": session_ready,
            "identity_ready": identity_ready,
            "governance_ready": governance_ready,
            "audit_ready": audit_ready,
            "ready": all([discovery_ready, workflow_ready, session_ready, identity_ready, governance_ready, audit_ready]),
        }
