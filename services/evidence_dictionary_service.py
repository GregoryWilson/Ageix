from __future__ import annotations

from models.consultation import EvidenceDictionary, EvidenceDictionaryItem
from models.work_packet import WorkPacket
from services.token_estimation_service import TokenEstimationService


class EvidenceDictionaryService:
    """Build requestable, grounded evidence menus for consultation participants."""

    def __init__(self) -> None:
        self.token_estimator = TokenEstimationService()

    def build_dictionary(self, work_packet: WorkPacket) -> EvidenceDictionary:
        dictionary = EvidenceDictionary(objective=work_packet.objective)

        if work_packet.planner_revisit_required or work_packet.unresolved_target_files:
            dictionary.excluded_reasons.append("unresolved_targets_present")
            dictionary.estimated_total_tokens = 0
            return dictionary

        approved_scope = self._unique(work_packet.approved_scope or work_packet.approved_target_files)
        if approved_scope:
            dictionary.items.append(self._item(
                evidence_id="EV-001",
                evidence_type="approved_scope",
                summary=f"Approved consultation scope containing {len(approved_scope)} grounded path(s).",
                payload=approved_scope,
                paths=approved_scope,
                requestable=False,
            ))

        if work_packet.repository_evidence:
            dictionary.items.append(self._item(
                evidence_id="EV-002",
                evidence_type="repository_summary",
                summary="Repository evidence summaries supplied by repository intelligence.",
                payload=work_packet.repository_evidence,
                paths=[p for p in work_packet.repository_evidence if isinstance(p, str) and "/" in p],
            ))

        if work_packet.discovery_evidence:
            dictionary.items.append(self._item(
                evidence_id="EV-003",
                evidence_type="dependency_summary",
                summary="Discovery/dependency evidence relevant to the approved scope.",
                payload=work_packet.discovery_evidence,
                reference_only=True,
            ))

        if work_packet.impact_summary or work_packet.impacted_files or work_packet.impacted_tests:
            payload = {
                "impact_summary": work_packet.impact_summary,
                "impacted_files": work_packet.impacted_files,
                "impacted_tests": work_packet.impacted_tests,
            }
            dictionary.items.append(self._item(
                evidence_id="EV-004",
                evidence_type="impact_summary",
                summary="Repository impact evidence for files affected by approved scope.",
                payload=payload,
                paths=self._unique(work_packet.impacted_files + work_packet.impacted_tests),
                reference_only=True,
            ))

        if work_packet.acceptance_criteria:
            dictionary.items.append(self._item(
                evidence_id="EV-005",
                evidence_type="acceptance_criteria",
                summary="Acceptance criteria for the current objective.",
                payload=work_packet.acceptance_criteria,
                requestable=False,
            ))

        if work_packet.test_targets:
            dictionary.items.append(self._item(
                evidence_id="EV-006",
                evidence_type="test_targets",
                summary="Grounded test targets associated with the approved work.",
                payload=work_packet.test_targets,
                paths=work_packet.test_targets,
            ))

        dictionary.estimated_total_tokens = sum(item.estimated_tokens for item in dictionary.items)
        return dictionary

    def _item(
        self,
        *,
        evidence_id: str,
        evidence_type: str,
        summary: str,
        payload: object,
        paths: list[str] | None = None,
        requestable: bool = True,
        reference_only: bool = False,
    ) -> EvidenceDictionaryItem:
        return EvidenceDictionaryItem(
            evidence_id=evidence_id,
            evidence_type=evidence_type,  # type: ignore[arg-type]
            summary=summary,
            estimated_tokens=self.token_estimator.estimate_payload_tokens(payload),
            paths=self._unique(paths or []),
            requestable=requestable,
            reference_only=reference_only,
            payload=payload,
        )

    def _unique(self, values: list[str]) -> list[str]:
        return [v for v in dict.fromkeys(values) if isinstance(v, str) and v]
