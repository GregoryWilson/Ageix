from __future__ import annotations

from typing import Any

from models.governance_review_packet import GovernanceReviewPacket
from models.promotion_readiness import PromotionReadinessResult


class GovernanceReviewPacketService:
    """Builds a human-reviewable packet for governed patch promotion decisions."""

    def build_packet(
        self,
        *,
        objective: str,
        implementation_summary: str,
        changed_files: list[str],
        requirement_trace: dict[str, Any] | None = None,
        behavior_verification: dict[str, Any] | None = None,
        validation_evidence: dict[str, Any] | None = None,
        runtime_evidence: dict[str, Any] | None = None,
        confidence_summary: dict[str, Any] | None = None,
        promotion_readiness: PromotionReadinessResult,
    ) -> GovernanceReviewPacket:
        trace = requirement_trace or {}
        return GovernanceReviewPacket(
            objective=objective,
            implementation_summary=implementation_summary,
            changed_files=changed_files,
            requirement_traces=trace.get("traces", []),
            behavioral_evidence=behavior_verification or {},
            validation_evidence=validation_evidence or {},
            runtime_evidence=runtime_evidence or {},
            confidence_summary=confidence_summary or {},
            blockers=promotion_readiness.blockers,
            promotion_recommendation=promotion_readiness.recommendation,
        )

    def metadata(self, packet: GovernanceReviewPacket) -> dict[str, Any]:
        return {
            "generated": True,
            "changed_file_count": len(packet.changed_files),
            "blocker_count": len(packet.blockers),
            "recommendation": packet.promotion_recommendation,
        }
