from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable

from models.capability_definition import CapabilityDefinition


class CapabilityRegistryService:
    """Discovers and registers governed Ageix capabilities."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
        self.discover_capabilities()

    def register(self, definition: CapabilityDefinition, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> CapabilityDefinition:
        self._capabilities[definition.capability_id] = definition
        self._handlers[definition.capability_id] = handler
        return definition

    def lookup(self, capability_id: str) -> CapabilityDefinition | None:
        return self._capabilities.get(capability_id)

    def exists(self, capability_id: str) -> bool:
        return capability_id in self._capabilities

    def list_capabilities(self) -> list[CapabilityDefinition]:
        return sorted(self._capabilities.values(), key=lambda item: item.capability_id)

    def handler_for(self, capability_id: str) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
        return self._handlers.get(capability_id)

    def discover_capabilities(self) -> None:
        package_name = "services.capabilities"
        package = importlib.import_module(package_name)
        for module_info in pkgutil.iter_modules(package.__path__):
            if module_info.name.startswith("_"):
                continue
            module = importlib.import_module(f"{package_name}.{module_info.name}")
            factory = getattr(module, "register_capabilities", None)
            if callable(factory):
                for definition, handler_factory in factory(self.repo_root):
                    self.register(definition, handler_factory)
