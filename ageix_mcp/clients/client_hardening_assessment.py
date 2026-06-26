from __future__ import annotations

from typing import Any


class MCPClientHardeningAssessmentService:
    """Summarizes MCP trust-boundary and abuse-test hardening evidence."""

    REQUIRED = {
        "denylist_enforced",
        "unknown_clients_denied",
        "placeholder_clients_denied",
        "provider_mismatch_denied",
        "impersonation_denied",
        "session_identity_drift_denied",
        "trusted_client_abuse_denied",
        "audit_failures_recorded",
    }

    def assess(self, *, client_id: str, validation: dict[str, Any]) -> dict[str, object]:
        passed = {key for key in self.REQUIRED if bool(validation.get(key))}
        return {
            "client_id": client_id,
            "admission_hardened": all(validation.get(key) for key in ["denylist_enforced", "unknown_clients_denied", "placeholder_clients_denied"]),
            "impersonation_hardened": all(validation.get(key) for key in ["provider_mismatch_denied", "impersonation_denied", "session_identity_drift_denied"]),
            "abuse_hardened": bool(validation.get("trusted_client_abuse_denied")),
            "audit_hardened": bool(validation.get("audit_failures_recorded")),
            "passed_checks": sorted(passed),
            "missing_checks": sorted(self.REQUIRED - passed),
            "hardened": self.REQUIRED == passed,
        }
