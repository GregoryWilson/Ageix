# agents/dispatcher.py

from importlib import import_module
from typing import Any

from agents.registry import get_agent


def _load_handler(handler_path: str):
    module_path, function_name = handler_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, function_name)


def dispatch_agent(agent_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent = get_agent(agent_key)
    handler = _load_handler(agent["handler"])

    return handler(payload)