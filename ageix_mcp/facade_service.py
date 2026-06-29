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


MCP_EXTERNAL_EXCLUDED_CAPABILITIES = {
    "decision.trace.create",
}


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

    def list_capabilities(self, *, exposed_only: bool = True, category: str | None = None, query: str | None = None, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        capabilities = self.capability_registry.list_capabilities()
        if exposed_only:
            capabilities = [
                definition for definition in capabilities
                if definition.exposed_to_external_agents
                and definition.capability_id not in MCP_EXTERNAL_EXCLUDED_CAPABILITIES
            ]
        if category:
            capabilities = [definition for definition in capabilities if definition.category == category]
        if query:
            lowered = str(query).lower()
            capabilities = [
                definition for definition in capabilities
                if lowered in definition.capability_id.lower()
                or lowered in definition.category.lower()
                or lowered in definition.description.lower()
                or lowered in definition.handler.lower()
            ]
        start = max(0, int(offset or 0))
        end = None if limit is None else start + max(0, int(limit or 0))
        return [definition.model_dump() for definition in capabilities[start:end]]

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
            category = str(arguments.get("category") or "") or None
            query = str(arguments.get("query") or "") or None
            limit = arguments.get("limit")
            offset = int(arguments.get("offset") or 0)
            tools = self.discover_tools(category=category)
            if query:
                lowered = query.lower()
                tools = [tool_def for tool_def in tools if lowered in str(tool_def.get("tool_name") or "").lower() or lowered in str(tool_def.get("description") or "").lower() or lowered in str(tool_def.get("category") or "").lower()]
            total = len(tools)
            start = max(0, offset)
            end = None if limit is None else start + max(0, int(limit or 0))
            tools = tools[start:end]
            capabilities = self.list_capabilities(category=category, query=query, limit=int(limit) if limit is not None else None, offset=offset)
            return AgeixEnvelope.ok(
                {"tools": tools, "categories": self.discover_categories(), "capabilities": capabilities, "count": len(tools), "total_count": total, "limit": limit, "offset": offset, "filters": {"category": category, "query": query}},
                tool_name=tool.name,
                capability_id=tool.capability_id,
            )
        if tool.capability_id == "capabilities.execute":
            requested = str(arguments.get("capability_id") or "")
            if not requested:
                return AgeixEnvelope.denied("capability_id_required", tool_name=tool.name)
            if requested in MCP_EXTERNAL_EXCLUDED_CAPABILITIES:
                return AgeixEnvelope.denied("capability_not_exposed_to_external_agents", tool_name=tool.name, capability_id=requested)
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
        if context.client_user_agent:
            merged_arguments["client_user_agent"] = context.client_user_agent
        if context.client_headers:
            merged_arguments["client_headers"] = context.client_headers
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
            metadata={
                **({"client_user_agent": context.client_user_agent} if context.client_user_agent else {}),
                **({"client_headers": context.client_headers} if context.client_headers else {}),
            },
        ))
        return AgeixEnvelope.denied(
            validation.reason,
            security_violation=validation.security_violation,
            tool_name=tool_name,
            capability_id=capability_id,
            client_trust=validation.metadata or {},
        )
