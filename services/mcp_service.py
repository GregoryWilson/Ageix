from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixEnvelope, AgeixRequestContext


class MCPService:
    """MCP-ready service layer for tool discovery, mapping, and governed execution.

    This class intentionally contains no transport authority. HTTP/SSE, stdio, and
    future MCP transports should all call this service, which then delegates to
    Ageix governed capability execution.
    """

    TOOL_PREFIX = "ageix."

    SPECIALIZED_TOOL_MAP = {
        "ageix.health": "ageix.health",
        "ageix.capabilities.list": "capabilities.list",
        "ageix.capabilities.execute": "capabilities.execute",
        "ageix.projects.current": "project.current",
        "ageix.projects.profile": "project.profile",
        "ageix.projects.list": "project.list",
        "ageix.proposals.submit": "proposal.submit",
        "ageix.proposals.get": "proposal.details",
        "ageix.proposals.list": "proposal.list",
        "ageix.proposals.status": "proposal.status",
        "ageix.consultations.submit": "consultation.submit",
        "ageix.consultations.get": "consultation.details",
        "ageix.consultations.list": "consultation.list",
        "ageix.audit.recent": "audit.recent",
    }

    RESERVED_SANDBOX_TOOLS = {
        "ageix.validation.scenarios.list": "placeholder_reserved_for_validation_sandbox",
        "ageix.validation.scenario.request": "placeholder_reserved_for_validation_sandbox",
        "ageix.validation.result.get": "placeholder_reserved_for_validation_sandbox",
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = CapabilityRegistryService(self.repo_root)
        self.execution = CapabilityExecutionService(self.repo_root)

    def build_session_context(self, payload: dict[str, Any]) -> AgeixRequestContext:
        return AgeixRequestContext(**payload)

    def discover_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool_name, capability_id in sorted(self.SPECIALIZED_TOOL_MAP.items()):
            if capability_id == "capabilities.execute":
                description = "Execute a governed Ageix capability by ID."
            elif capability_id == "capabilities.list":
                description = "List governed Ageix capabilities exposed to external clients."
            else:
                definition = self.registry.lookup(capability_id)
                description = definition.description if definition else "Governed Ageix tool."
            tools.append({"tool_name": tool_name, "capability_id": capability_id, "description": description})
        for tool_name, reason in sorted(self.RESERVED_SANDBOX_TOOLS.items()):
            tools.append({"tool_name": tool_name, "capability_id": None, "reserved": True, "description": reason})
        return tools

    def map_capability(self, tool_name: str) -> str | None:
        return self.SPECIALIZED_TOOL_MAP.get(tool_name)

    def execute_tool(self, tool_name: str, context: AgeixRequestContext, arguments: dict[str, Any] | None = None) -> AgeixEnvelope:
        if tool_name in self.RESERVED_SANDBOX_TOOLS:
            return AgeixEnvelope.denied(self.RESERVED_SANDBOX_TOOLS[tool_name], tool_name=tool_name)
        capability_id = self.map_capability(tool_name)
        if not capability_id:
            return AgeixEnvelope.denied("unknown_mcp_tool", tool_name=tool_name)
        if capability_id == "capabilities.list":
            return AgeixEnvelope.ok({"tools": self.discover_tools(), "capabilities": self.list_capabilities()})
        if capability_id == "capabilities.execute":
            requested = str((arguments or {}).get("capability_id") or "")
            if not requested:
                return AgeixEnvelope.denied("capability_id_required", tool_name=tool_name)
            return self.execute_capability(requested, context, (arguments or {}).get("arguments") or {})
        return self.execute_capability(capability_id, context, arguments or {})

    def execute_capability(self, capability_id: str, context: AgeixRequestContext, arguments: dict[str, Any] | None = None) -> AgeixEnvelope:
        merged_arguments = {**(arguments or {}), "project_id": context.project_id, "client_id": context.client_id}
        if context.participant_id:
            merged_arguments["participant_id"] = context.participant_id
        response = self.execution.execute(CapabilityRequest(
            capability_id=capability_id,
            session_id=context.session_id,
            agent_id=context.agent_id,
            arguments=merged_arguments,
        ))
        return AgeixEnvelope(
            success=response.success,
            result=response.result,
            errors=[response.error] if response.error else [],
            governance={
                "capability_id": capability_id,
                "authorization_reason": response.metadata.get("authorization_reason"),
                "chair_authority_preserved": True,
            },
            metadata=response.metadata,
        )

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [definition.model_dump() for definition in self.registry.list_capabilities()]
