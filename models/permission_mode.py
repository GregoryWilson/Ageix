from __future__ import annotations

from enum import Enum


class PermissionMode(str, Enum):
    """Worker admission permission modes, per ADR-0014 (Worker Admission).

    A permission mode describes how autonomously an admitted worker may act.
    It grants participation posture only — never authority. Ageix remains the
    authoritative store for identity, scope, DevJob state, and governance.

      - supervised:        worker acts step-by-step under supervision.
      - constrained_auto:  worker may proceed automatically within scope, but
                           still blocks on ambiguity, missing evidence, unsafe
                           instructions, or scope conflict.
      - sandbox_auto:      automatic execution inside an approved sandbox policy;
                           still blocks on the same governed stop conditions.
    """

    SUPERVISED = "supervised"
    CONSTRAINED_AUTO = "constrained_auto"
    SANDBOX_AUTO = "sandbox_auto"

    @classmethod
    def is_valid(cls, value: str | None) -> bool:
        if value is None:
            return False
        return value in {mode.value for mode in cls}

    @classmethod
    def parse(cls, value: str | None) -> "PermissionMode":
        """Return the matching mode or raise ValueError with an explicit reason."""
        if not cls.is_valid(value):
            raise ValueError("worker_admission_invalid_permission_mode")
        return cls(str(value))
