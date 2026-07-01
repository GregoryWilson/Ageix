from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from models.worker_admission_ticket import WorkerAdmissionTicket
from models.worker_launch_profile import WorkerLaunchProfile
from models.worker_launch_request import WorkerLaunchRequest


@dataclass
class LauncherHandoff:
    """The transport-only output of a launcher adapter.

    Contains manual handoff instructions and a non-authoritative launch
    reference. It never carries executable authority — an admitted worker must
    still retrieve governed context from Ageix before acting.
    """

    handoff_instructions: list[str]
    launch_reference: dict[str, Any]
    adapter_notes: list[str] = field(default_factory=list)


class LauncherAdapter(ABC):
    """Abstraction for a governed manual worker handoff.

    A LauncherAdapter is a transport concept under Worker Admission (ADR-0014):
    it assembles non-authoritative handoff instructions for a specific worker
    surface. It must NOT execute a worker, manage a process, capture output,
    register callbacks, sequence validation, or apply patches.
    """

    adapter_key: str = ""
    expected_worker_type: str | None = None

    @abstractmethod
    def build_handoff(
        self,
        *,
        ticket: WorkerAdmissionTicket,
        profile: WorkerLaunchProfile,
        request: WorkerLaunchRequest,
    ) -> LauncherHandoff:
        """Assemble the non-authoritative handoff for this adapter's surface."""
        raise NotImplementedError
