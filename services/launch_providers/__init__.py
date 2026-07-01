from __future__ import annotations

from pathlib import Path

from services.launch_providers.base import (
    LaunchContext,
    LaunchOutcome,
    LaunchProvider,
)
from services.launch_providers.local_command import ClaudeCodeCliLaunchProvider


def default_providers(repo_root: str | Path = ".") -> list[LaunchProvider]:
    """The launch providers Ageix knows about. Governance does not depend on
    this list; it is resolved behind the Worker Launcher subsystem. Add future
    workers here (Anthropic CLI, tmux, Docker, remote) without touching
    governance, conversation, or DevJob services."""
    return [ClaudeCodeCliLaunchProvider(repo_root)]


def resolve_launch_provider(
    repo_root: str | Path = ".",
    *,
    worker_type: str | None = None,
    providers: list[LaunchProvider] | None = None,
) -> LaunchProvider | None:
    """Return the first available provider that can engage `worker_type`, or None
    (in which case the bridge creates a durable queued launch request)."""
    candidates = providers if providers is not None else default_providers(repo_root)
    for provider in candidates:
        if worker_type and provider.worker_type and provider.worker_type != worker_type:
            continue
        if provider.is_available():
            return provider
    return None


__all__ = [
    "LaunchContext",
    "LaunchOutcome",
    "LaunchProvider",
    "ClaudeCodeCliLaunchProvider",
    "default_providers",
    "resolve_launch_provider",
]
