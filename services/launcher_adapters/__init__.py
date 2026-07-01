from __future__ import annotations

from services.launcher_adapters.base import LauncherAdapter, LauncherHandoff
from services.launcher_adapters.chatgpt_devworker_manual import ChatGPTDevWorkerManualLauncherAdapter
from services.launcher_adapters.claude_code_browser import ClaudeCodeBrowserLauncherAdapter

# Registry of governed manual-handoff adapters, keyed by adapter key. Adapters
# are transport-only: they assemble non-authoritative handoff instructions and
# never execute, manage, or observe a worker process.
LAUNCHER_ADAPTERS: dict[str, LauncherAdapter] = {
    adapter.adapter_key: adapter
    for adapter in (
        ClaudeCodeBrowserLauncherAdapter(),
        ChatGPTDevWorkerManualLauncherAdapter(),
    )
}


def get_adapter(adapter_key: str) -> LauncherAdapter:
    adapter = LAUNCHER_ADAPTERS.get(str(adapter_key or ""))
    if adapter is None:
        raise ValueError("worker_launcher_adapter_not_supported")
    return adapter


__all__ = [
    "LauncherAdapter",
    "LauncherHandoff",
    "ClaudeCodeBrowserLauncherAdapter",
    "ChatGPTDevWorkerManualLauncherAdapter",
    "LAUNCHER_ADAPTERS",
    "get_adapter",
]
