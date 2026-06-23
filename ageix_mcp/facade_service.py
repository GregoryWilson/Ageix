from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_audit_record import CapabilityAuditRecord
from models.capability_request import CapabilityRequest
from ageix_mcp.discovery_service import MCPDiscoveryService
from ageix_mcp.tool_registry import MCPToolRegistry
from ageix_mcp.clients.client_trust_validator import MCPClientTrustValidator
from services.capability_audit_service import CapabilityAuditService
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
        self.trust = MCPClientTrustValidator(str(self.repo_root))
        self.audit = CapabilityAuditService(self.repo_root)

    def build_session_context(self, payload: dict[str, Any]) -> AgeixRequestContext:
        return AgeixRequestContext(**payload)

    def discover_tools(
        self,
        *,
        category: str | None = None,
        experimental: bool | None = None,
        include_placeholders: bool = True,
        include_disabled: bool = False,
        exposed_only: bool = True,
    ) -> list[dict[str, Any]]:
        return MCPDiscoveryService(self.tool_registry, self.capability_registry).discover_tools(
            category=category,
            experimental=experimental,
            include_placeholders=include_placeholders,
            include_disabled=include_disabled,
            exposed_only=exposed_only,
        )

    def discover_categories(self, *, include_placeholders: bool = True, exposed_only: bool = True) -> list[dict[str, Any]]:
        return MCPDiscoveryService(self.tool_registry, self.capability_registry).categories(
            include_placeholders=include_placeholders,
            exposed_only=exposed_only,
        )

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [definition.model_dump() for definition in self.capability_registry.list_capabilities()]

    def execute_tool(
        self,
        tool_name: str,
        context: AgeixRequestContext,
        arguments: dict[str, Any] | None = None,
    ) -> AgeixEnvelope:
        trust = self._validate_client_trust(context, tool_name=tool_name, capability_id=None)
        if trust is not None:
            return trust

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
                {"tools": self.discover_tools(), "categories": self.discover_categories(), "capabilities": self.list_capabilities()},
                tool_name=tool.name,
                capability_id=tool.capability_id,
            )
        if tool.capability_id == "capabilities.execute":
            requested = str(arguments.get("capability_id") or "")
            if not requested:
                return AgeixEnvelope.denied("capability_id_required", tool_name=tool.name)
            nested_arguments = arguments.get("arguments") or {}
            if requested == "evidence.package.reuse" and not self._has_reuse_governance_context(nested_arguments):
                return AgeixEnvelope.denied("proposal_context_required_for_package_reuse", tool_name=tool.name, capability_id=requested)
            return self.execute_capability(requested, context, nested_arguments, tool_name=tool.name)

        if tool.capability_id == "evidence.package.reuse" and not self._has_reuse_governance_context(arguments):
            return AgeixEnvelope.denied("proposal_context_required_for_package_reuse", tool_name=tool.name, capability_id=tool.capability_id)

        return self.execute_capability(tool.capability_id, context, arguments, tool_name=tool.name)

    def execute_capability(
        self,
        capability_id: str,
        context: AgeixRequestContext,
        arguments: dict[str, Any] | None = None,
        *,
        tool_name: str | None = None,
    ) -> AgeixEnvelope:
        trust = self._validate_client_trust(context, tool_name=tool_name, capability_id=capability_id)
        if trust is not None:
            return trust

        forbidden = {"authorization", "token", "bearer_token"}.intersection(set((arguments or {}).keys()))
        if forbidden:
            return AgeixEnvelope.denied("credential_fields_not_allowed", capability_id=capability_id)
        merged_arguments = {
            **(arguments or {}),
            "project_id": context.project_id,
            "client_id": context.client_id,
            "client_context": self.trust.build_client_context(context),
            "authentication_method": context.authentication_method,
        }
        if context.participant_id:
            merged_arguments["participant_id"] = context.participant_id
        if context.provider:
            merged_arguments["provider"] = context.provider
        if context.display_name:
            merged_arguments["display_name"] = context.display_name
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


    def _has_reuse_governance_context(self, arguments: dict[str, Any]) -> bool:
        if arguments.get("proposal_id") or arguments.get("evidence_plan_id"):
            return True
        chair_approval = arguments.get("chair_approval")
        return isinstance(chair_approval, dict) and bool(chair_approval.get("approved"))


    def _validate_client_trust(self, context: AgeixRequestContext, *, tool_name: str | None, capability_id: str | None) -> AgeixEnvelope | None:
        validation = self.trust.validate(context)
        if validation.allowed:
            return None
        denied_capability = capability_id or tool_name or "mcp.client.admission"
        self.audit.record(CapabilityAuditRecord(
            session_id=context.session_id,
            agent_id=context.agent_id,
            capability_id=str(denied_capability),
            success=False,
            reason=validation.reason,
            client_id=context.client_id,
            project_id=context.project_id,
            participant_id=context.participant_id,
        ))
        return AgeixEnvelope.denied(
            validation.reason,
            security_violation=validation.security_violation,
            tool_name=tool_name,
            capability_id=capability_id,
            client_trust=validation.metadata or {},
        )
