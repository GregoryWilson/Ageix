from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCommandResult:
    command: str
    return_code: int
    duration_seconds: float
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.return_code == 0


class TestExecutionService:
    def run_commands(
        self,
        workspace_path: Path,
        commands: list[str],
        timeout_seconds: int = 120,
    ) -> list[TestCommandResult]:
        results: list[TestCommandResult] = []

        for command in commands:
            started = time.perf_counter()

            completed = subprocess.run(
                command,
                cwd=workspace_path,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            duration = time.perf_counter() - started

            results.append(
                TestCommandResult(
                    command=command,
                    return_code=completed.returncode,
                    duration_seconds=round(duration, 3),
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )

        return results