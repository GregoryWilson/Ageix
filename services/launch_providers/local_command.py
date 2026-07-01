from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from services.launch_providers.base import LaunchContext, LaunchOutcome, LaunchProvider

#: Operator opt-in: a shell command template that starts the worker. When unset,
#: this provider reports itself unavailable and the bridge queues instead. This
#: is the ONLY place a concrete Claude Code invocation lives — never governance.
LAUNCH_CMD_ENV = "AGEIX_CLAUDE_CODE_LAUNCH_CMD"


class ClaudeCodeCliLaunchProvider(LaunchProvider):
    """Engages Claude Code via a locally-configured launch command, per Sprint 21.5.

    Availability is opt-in: the operator configures a command template (env
    AGEIX_CLAUDE_CODE_LAUNCH_CMD, or an explicit command passed in). If nothing
    is configured, the provider is unavailable and the bridge falls back to a
    durable queued launch request. When available it spawns the command detached
    and returns the process reference — governance never learns how this works.
    """

    provider_key = "claude_code_cli"
    worker_type = "claude_code"

    def __init__(self, repo_root: str | Path = ".", *, command: str | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        # Explicit command wins; otherwise read the operator opt-in env var.
        self._command = command if command is not None else os.environ.get(LAUNCH_CMD_ENV)

    def is_available(self) -> bool:
        return bool(str(self._command or "").strip())

    def launch(self, context: LaunchContext) -> LaunchOutcome:
        command = str(self._command or "").strip()
        if not command:
            return LaunchOutcome(launched=False, error="launch_provider_unavailable",
                                 detail="No launch command configured.")
        try:
            args = shlex.split(command)
        except ValueError as exc:
            return LaunchOutcome(launched=False, error="launch_provider_bad_command", detail=str(exc))

        # Pass the governed references to the worker via the environment only.
        # The worker still redeems its admission ticket and retrieves context
        # from Ageix through the governed MCP surface after it starts.
        child_env = {
            **os.environ,
            "AGEIX_DEVJOB_ID": context.devjob_id,
            "AGEIX_WORKER_ID": context.worker_id,
            "AGEIX_PROJECT_ID": context.project_id,
            "AGEIX_ADMISSION_TICKET_ID": context.admission_ticket_id or "",
            "AGEIX_LAUNCH_ARTIFACT_ID": context.launch_artifact_id or "",
            "AGEIX_REQUIRED_NEXT_CAPABILITY": context.required_next_capability,
        }
        try:
            proc = subprocess.Popen(  # noqa: S603 - operator-configured command
                args,
                cwd=str(self.repo_root),
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return LaunchOutcome(launched=False, error="launch_provider_spawn_failed", detail=str(exc))

        return LaunchOutcome(
            launched=True,
            session_ref={
                "provider": self.provider_key,
                "pid": proc.pid,
                "command": args[0],
                "worker_type": self.worker_type,
            },
            detail=f"Launched via {self.provider_key} (pid={proc.pid}).",
        )
