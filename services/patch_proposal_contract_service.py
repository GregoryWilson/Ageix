from __future__ import annotations

from copy import deepcopy
from typing import Any

from models.patch_proposal_contract import PatchProposalNormalizationEvidence


class PatchProposalContractService:
    """Normalize and validate DevWorker patch proposal contracts."""

    REQUIRED_FIELDS = [
        "result_type",
        "objective",
        "summary",
        "files_considered",
        "evidence_used",
        "dependency_hints_used",
        "assumptions",
        "dependency_risks",
        "changes",
        "test_plan",
        "no_write_confirmation",
    ]

    CHANGE_ALIASES = ["changes", "proposed_changes", "patch", "files"]
    TEST_PLAN_ALIASES = ["test_plan", "tests"]

    def normalize(
        self,
        proposal: dict[str, Any],
        *,
        source_agent: str | None = None,
        retry_count: int = 0,
    ) -> tuple[dict[str, Any], PatchProposalNormalizationEvidence]:
        normalized = deepcopy(proposal or {})
        raw_field_names = sorted(normalized.keys())
        missing_before = self.missing_required_fields(normalized)
        normalized_from: dict[str, str] = {}

        if "changes" not in normalized or not self._non_empty_list(normalized.get("changes")):
            for alias in self.CHANGE_ALIASES:
                value = normalized.get(alias)
                if alias == "changes":
                    continue
                if self._non_empty_list(value):
                    normalized["changes"] = value
                    normalized_from["changes"] = alias
                    break
                if "changes" not in normalized and isinstance(value, list):
                    normalized["changes"] = value
                    normalized_from["changes"] = alias
                    break

        if "test_plan" not in normalized or not self._non_empty_list(normalized.get("test_plan")):
            for alias in self.TEST_PLAN_ALIASES:
                value = normalized.get(alias)
                if alias != "test_plan" and self._non_empty_list(value):
                    normalized["test_plan"] = value
                    normalized_from["test_plan"] = alias
                    break

        # Keep both legacy and canonical fields populated to support older
        # Chair/DevWorker checks while using changes as the canonical contract.
        if self._non_empty_list(normalized.get("changes")) and not self._non_empty_list(normalized.get("proposed_changes")):
            normalized["proposed_changes"] = normalized["changes"]
            normalized_from.setdefault("proposed_changes", "changes")

        normalized.setdefault("agent", source_agent or proposal.get("agent") or "devworker")
        normalized.setdefault("mode", proposal.get("mode") or "proposal_only")
        normalized.setdefault("notes", [])
        normalized.setdefault("files_considered", [])
        normalized.setdefault("evidence_used", [])
        normalized.setdefault("dependency_hints_used", [])
        normalized.setdefault("assumptions", [])
        normalized.setdefault("dependency_risks", [])
        normalized.setdefault("test_plan", [])
        normalized.setdefault("no_write_confirmation", True)

        missing_after = self.missing_required_fields(normalized)
        evidence = PatchProposalNormalizationEvidence(
            raw_field_names=raw_field_names,
            normalized_field_names=sorted(normalized.keys()),
            missing_fields_before_normalization=missing_before,
            missing_fields_after_normalization=missing_after,
            normalized_from=normalized_from,
            source_agent=source_agent or normalized.get("agent"),
            retry_count=retry_count,
        )
        normalized["patch_proposal_normalization_evidence"] = evidence.model_dump()
        return normalized, evidence

    def missing_required_fields(self, proposal: dict[str, Any]) -> list[str]:
        return [field for field in self.REQUIRED_FIELDS if field not in proposal]


    def validate_approved_scope(
        self,
        proposal: dict[str, Any],
        *,
        approved_scope: list[str] | None = None,
    ) -> None:
        """Reject DevWorker proposals that modify files outside Planner-approved scope."""
        scope = set(approved_scope or [])
        if not scope:
            return
        proposed = {
            str(change.get("path", "")).strip()
            for change in proposal.get("changes", []) or []
            if isinstance(change, dict)
        }
        unapproved = sorted(path for path in proposed if path and path not in scope)
        if unapproved:
            raise ValueError(
                "scope_validation_failed: proposal_targets must be within approved_scope; "
                f"unapproved={unapproved}"
            )

    def architecture_scope_exceeded_request(
        self,
        *,
        requested_files: list[str],
        reason: str = "architecture_scope_exceeded",
    ) -> dict[str, Any]:
        return {
            "result_type": "context_request",
            "reason": reason,
            "requested_files": sorted(dict.fromkeys(requested_files)),
            "recommended_planner_revisit": True,
        }

    def classify_validation_failure(self, proposal: dict[str, Any]) -> str | None:
        if "changes" not in proposal:
            return "missing_changes_field"
        if not isinstance(proposal.get("changes"), list) or not proposal.get("changes"):
            return "empty_patch_proposal"
        for change in proposal.get("changes", []):
            if not isinstance(change, dict):
                return "invalid_patch_operation"
            if change.get("operation") not in {"replace_file", "create_file"}:
                return "invalid_patch_operation"
        return None

    @staticmethod
    def _non_empty_list(value: Any) -> bool:
        return isinstance(value, list) and bool(value)
