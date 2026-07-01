from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LaunchContext:
    """Everything a launch provider needs to engage a worker — and nothing about
    governance. Providers receive references only; they must not evaluate
    authority (that already happened upstream in the governed bridge)."""

    devjob_id: str
    worker_id: str
    project_id: str
    admission_ticket_id: str | None = None
    launch_artifact_id: str | None = None
    required_next_capability: str = "devjob.get"
    handoff_instructions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LaunchOutcome:
    """The result of a provider attempting to engage a worker.

    launched=True  -> a worker was engaged; session_ref identifies it.
    launched=False -> the provider could not satisfy the request; the bridge
                      falls back to a durable queued launch request. `error`
                      distinguishes "unavailable" (queue) from a real failure.
    """

    launched: bool
    session_ref: dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    error: str | None = None


class LaunchProvider(ABC):
    """Abstraction that actually engages a worker process, per Sprint 21.5.

    This is the seam that keeps Ageix governance from ever needing to know HOW a
    worker (Claude Code CLI, Anthropic CLI, a local wrapper, tmux, Docker, a
    future remote worker) is launched. Governance depends on this interface, not
    on any concrete provider. A provider that cannot satisfy a request returns
    an explicit unavailable/failed outcome without compromising governance.
    """

    provider_key: str = ""
    #: The worker_type this provider can engage (matched against the launch profile).
    worker_type: str | None = None

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider is configured and able to launch right now."""
        raise NotImplementedError

    @abstractmethod
    def launch(self, context: LaunchContext) -> LaunchOutcome:
        """Attempt to engage the worker. Must never raise for expected
        conditions — return a LaunchOutcome with launched=False instead."""
        raise NotImplementedError
