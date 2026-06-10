from __future__ import annotations

from pathlib import Path

from services.controls_service import ControlsService


class GovernancePolicyService:
    """
    Central policy layer for Ageix authority decisions.

    Controls may tune bounded behavior, but this service enforces
    non-negotiable governance locks.
    """

    def __init__(
        self,
        repo_root: Path | str = ".",
        controls_service: ControlsService | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.controls = controls_service or ControlsService(self.repo_root)

    def maximum_local_repair_attempts(self) -> int:
        return max(0, self.controls.repair.max_local_attempts)

    def may_escalate_to_cloud(self) -> bool:
        return bool(self.controls.repair.allow_cloud_escalation)

    def must_request_human_review(self) -> bool:
        return True

    def must_validate_patch(self) -> bool:
        return True

    def may_bypass_validation(self) -> bool:
        return False

    def may_promote_patch(self) -> bool:
        return False

    def may_commit_patch(self) -> bool:
        return False

    def may_modify_live_repository(self) -> bool:
        return False