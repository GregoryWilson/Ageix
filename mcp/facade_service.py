from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_request import CapabilityRequest
from mcp.tool_registry import MCPToolRegistry
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixEnvelope, AgeixRequestContext


class MCPFacadeService:
    """Transport-independent MCP facade over governed capability execution."""

    def __init__(self, repo_root: str | Path = ".", tool_registry: MCPToolRegistry | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.tool_registry = tool_registry or MCPToolRegistry()
        self.capability_registry = CapabilityRegistryService(self.repo_root)
        self.execution = CapabilityExecutionService(self.repo_root)

    def build_session_context(self, payload: dict[str, Any]) -> AgeixRequestContext:
        return AgeixRequestContext(**payload)

    def discover_tools(self) -> list[dict[str, object]]:
        return self.tool_registry.discover()

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [definition.model_dump() for definition in self.capability_registry.list_capabilities()]

    def execute_tool(
        self,
        tool_name: str,
        context: AgeixRequestContext,
        arguments: dict[str, Any] | None = None,
    ) -> AgeixEnvelope:
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return AgeixEnvelope.denied("unknown_mcp_tool", tool_name=tool_name)
        if not tool.enabled:
            return AgeixEnvelope.denied("mcp_tool_disabled", tool_name=tool_name)
        if tool.requires_project and not context.project_id:
            return AgeixEnvelope.denied("project_id_required", tool_name=tool_name)
        if tool.placeholder:
            friendly_reason = tool.placeholder_reason or "mcp_tool_not_implemented"
            legacy_reason = "placeholder_reserved_for_validation_sandbox"
            return AgeixEnvelope(
                success=False,
                result={},
                errors=[friendly_reason],
                governance={
                    "denied": True,
                    "reason": legacy_reason,
                    "friendly_reason": friendly_reason,
                    "security_violation": False,
                    "chair_authority_preserved": True,
                },
                metadata={
                    "tool_name": tool.name,
                    "capability_id": tool.capability_id,
                    "placeholder": True,
                    "experimental": tool.experimental,
                },
            )

        arguments = arguments or {}
        if tool.capability_id == "capabilities.list":
            return AgeixEnvelope.ok(
                {"tools": self.discover_tools(), "capabilities": self.list_capabilities()},
                tool_name=tool.name,
                capability_id=tool.capability_id,
            )
        if tool.capability_id == "capabilities.execute":
            requested = str(arguments.get("capability_id") or "")
            if not requested:
                return AgeixEnvelope.denied("capability_id_required", tool_name=tool.name)
            return self.execute_capability(requested, context, arguments.get("arguments") or {}, tool_name=tool.name)

        return self.execute_capability(tool.capability_id, context, arguments, tool_name=tool.name)

    def execute_capability(
        self,
        capability_id: str,
        context: AgeixRequestContext,
        arguments: dict[str, Any] | None = None,
        *,
        tool_name: str | None = None,
    ) -> AgeixEnvelope:
        merged_arguments = {
            **(arguments or {}),
            "project_id": context.project_id,
            "client_id": context.client_id,
        }
        if context.participant_id:
            merged_arguments["participant_id"] = context.participant_id
        response = self.execution.execute(CapabilityRequest(
            capability_id=capability_id,
            session_id=context.session_id,
            agent_id=context.agent_id,
            arguments=merged_arguments,
        ))
        governance = {
            "capability_id": capability_id,
            "tool_name": tool_name,
            "authorized": response.success,
            "decision": "approved" if response.success else "denied",
            "reason": response.error,
            "authorization_reason": response.metadata.get("authorization_reason"),
            "chair_authority_preserved": True,
        }
        return AgeixEnvelope(
            success=response.success,
            result=response.result,
            errors=[response.error] if response.error else [],
            governance=governance,
            metadata={"tool_name": tool_name, **response.metadata},
        )
