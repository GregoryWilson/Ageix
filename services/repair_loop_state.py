from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MAX_REPAIR_ATTEMPTS = 3


@dataclass
class RepairLoopState:
    original_patch_id: str
    attempts: int = 0
    repair_patch_ids: list[str] = field(default_factory=list)
    stopped: bool = False
    stop_reason: str = ""

    @property
    def can_attempt_repair(self) -> bool:
        return not self.stopped and self.attempts < MAX_REPAIR_ATTEMPTS

    def record_attempt(
        self,
        repair_patch_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.can_attempt_repair:
            self.stopped = True
            self.stop_reason = (
                f"Maximum repair attempts reached: {MAX_REPAIR_ATTEMPTS}"
            )
            return

        self.attempts += 1
        self.repair_patch_ids.append(repair_patch_id)

    def stop(self, reason: str) -> None:
        self.stopped = True
        self.stop_reason = reason