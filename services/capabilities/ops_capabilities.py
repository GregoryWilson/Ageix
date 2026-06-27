from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition

_RESTART_SCRIPT_RELATIVE_PATH = "scripts/Ops/restart_ageix.sh"
_DEFAULT_STOP_DELAY_SECONDS = 2


def register_capabilities(repo_root: Path):
    def restart_daemon(arguments: dict[str, Any]) -> dict[str, Any]:
        script_path = repo_root / _RESTART_SCRIPT_RELATIVE_PATH
        if not script_path.is_file() or not os.access(script_path, os.X_OK):
            return {"success": False, "result": {}, "error": "restart_script_missing_or_not_executable"}

        log_file = str(arguments.get("log_file") or "/tmp/ageix_uvicorn.log")
        stop_delay = int(arguments.get("stop_delay_seconds") or _DEFAULT_STOP_DELAY_SECONDS)
        env = {**os.environ, "STOP_DELAY": str(stop_delay), "LOG_FILE": log_file}

        # The handler runs inside the very process being restarted: detach the
        # script into its own session so the SIGTERM it sends to this process
        # doesn't also land on the script itself, and rely on STOP_DELAY so
        # this response has time to flush back to the caller first.
        subprocess.Popen(
            [str(script_path), "restart"],
            cwd=str(repo_root),
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {
            "success": True,
            "result": {
                "status": "restart_initiated",
                "log_file": log_file,
                "stop_delay_seconds": stop_delay,
                "note": "the server process will exit and a new one will start in its place; this connection will drop momentarily",
            },
            "metadata": {"source": "ops_restart"},
        }

    return [
        (
            CapabilityDefinition(
                capability_id="ops.restart_daemon",
                category="ops",
                access_level="governed_write",
                handler="ops.restart_daemon",
                description="Restart the Ageix server daemon via scripts/Ops/restart_ageix.sh, detached from the requesting process so it survives this process exiting.",
                exposed_to_external_agents=False,
            ),
            restart_daemon,
        ),
    ]
