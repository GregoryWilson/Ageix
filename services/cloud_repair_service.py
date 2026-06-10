from __future__ import annotations

from typing import Any


class CloudRepairService:
    """Executes a cloud repair escalation and returns a patch proposal."""

    def __init__(self, dev_worker: Any | None = None) -> None:
        self.dev_worker = dev_worker

    def execute_cloud_repair(
        self,
        escalation_packet: dict[str, Any],
    ) -> dict[str, Any]:
        if self.dev_worker is None:
            return {
                "status": "unavailable",
                "reason": "cloud_dev_worker_not_configured",
                "proposal": None,
            }

        try:
            proposal = self.dev_worker.generate_repair_proposal(
                escalation_packet,
                execution_target="cloud",
            )

            return {
                "status": "proposal_generated",
                "reason": None,
                "proposal": proposal,
            }

        except Exception as exc:
            return {
                "status": "unavailable",
                "reason": str(exc),
                "proposal": None,
            }