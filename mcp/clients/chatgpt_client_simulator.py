from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from mcp.clients.chatgpt_client_profile import ChatGPTClientProfile
from mcp.clients.client_readiness_service import ClientReadinessService
from mcp.facade_service import MCPFacadeService
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixRequestContext


@dataclass
class ChatGPTClientSimulationResult:
    client_id: str
    session_id: str
    discovery: list[dict[str, Any]]
    consumed_workflow_hints: list[str] = field(default_factory=list)
    responses: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "session_id": self.session_id,
            "discovery": self.discovery,
            "consumed_workflow_hints": self.consumed_workflow_hints,
            "responses": self.responses,
            "validation": self.validation,
            "readiness": self.readiness,
        }


class ChatGPTClientSimulator:
    """Compatibility harness proving Lex can navigate Ageix from MCP metadata.

    The harness chooses tools from discovered categories, schemas, and workflow
    hints. It does not contain special execution authority.
    """

    def __init__(self, repo_root: str = ".", facade: MCPFacadeService | None = None, profile: ChatGPTClientProfile | None = None) -> None:
        self.repo_root = repo_root
        self.facade = facade or MCPFacadeService(repo_root)
        self.profile = profile or ChatGPTClientProfile.resolve()

    def discover(self) -> list[dict[str, Any]]:
        return self.facade.discover_tools(include_placeholders=True, include_disabled=True)

    def discovery_snapshot(self) -> dict[str, Any]:
        tools = self.discover()
        return {
            "client": self.profile.to_dict(),
            "tool_count": len(tools),
            "capabilities": [tool["capability_id"] for tool in tools],
            "schemas": {tool["tool_name"]: tool.get("input_schema", {}) for tool in tools},
            "workflow_hints": {tool["tool_name"]: tool.get("recommended_next_tools", []) for tool in tools},
            "identity_tools": [tool["tool_name"] for tool in tools if tool.get("category") == "identity"],
            "session_tools": [tool["tool_name"] for tool in tools if tool.get("category") == "workflow"],
        }

    def run_validation(self, *, project_id: str, session_id: str | None = None, participant_id: str | None = "greg") -> ChatGPTClientSimulationResult:
        session_id = session_id or f"chatgpt-sim-{uuid4().hex[:8]}"
        context = AgeixRequestContext(
            client_id=self.profile.client_id,
            agent_id=self.profile.agent_id,
            participant_id=participant_id,
            session_id=session_id,
            project_id=project_id,
        )
        discovery = self.discover()
        by_name = {tool["tool_name"]: tool for tool in discovery}
        by_category: dict[str, list[dict[str, Any]]] = {}
        for tool in discovery:
            by_category.setdefault(str(tool.get("category")), []).append(tool)

        result = ChatGPTClientSimulationResult(self.profile.client_id, session_id, discovery)
        required_categories = {"proposal", "consultation", "project", "workflow", "identity", "audit"}
        schema_consumed = all(bool(tool.get("input_schema")) for tool in discovery if tool.get("category") in required_categories)

        workflow_tool = self._single_tool(by_category, "workflow")
        identity_tool = self._single_tool(by_category, "identity")
        proposal_tool = self._tool_by_capability(discovery, "proposal.submit")
        consultation_tool = self._tool_by_capability(discovery, "consultation.submit")
        status_tool = self._tool_by_capability(discovery, "proposal.status")
        audit_tool = self._single_tool(by_category, "audit")

        workflow_initial = self.facade.execute_tool(workflow_tool, context, {})
        identity = self.facade.execute_tool(identity_tool, context, {})
        proposal = self.facade.execute_tool(
            proposal_tool,
            context,
            self._arguments_from_schema(
                by_name[proposal_tool],
                objective="Lex MCP client validation proposal.",
                proposal_type="architecture",
                metadata={"client_validation": True},
            ),
        )
        proposal_id = str(proposal.metadata.get("proposal_id") or proposal.result.get("proposal", {}).get("proposal_id") or "")

        next_after_proposal = self._first_recommended(by_name[proposal_tool], category_tools=by_category, target_capability="consultation.submit")
        result.consumed_workflow_hints.append(next_after_proposal)
        consultation = self.facade.execute_tool(
            next_after_proposal,
            context,
            self._arguments_from_schema(
                by_name[next_after_proposal],
                consultation_type="architecture_review",
                summary="Lex simulator consumed MCP metadata and workflow hints successfully.",
                confidence=0.82,
                disposition="proceed",
                evidence_sufficient=True,
            ),
        )
        consultation_id = str(consultation.metadata.get("consultation_id") or consultation.result.get("consultation_id") or "")

        next_after_consultation = self._first_recommended(by_name[next_after_proposal], category_tools=by_category, target_capability="proposal.status")
        result.consumed_workflow_hints.append(next_after_consultation)
        status = self.facade.execute_tool(
            next_after_consultation,
            context,
            self._arguments_from_schema(by_name[next_after_consultation], proposal_id=proposal_id),
        )
        workflow_final = self.facade.execute_tool(workflow_tool, context, {})

        missing_link_denial = self.facade.execute_tool(
            consultation_tool,
            AgeixRequestContext(
                client_id=self.profile.client_id,
                agent_id=self.profile.agent_id,
                participant_id=participant_id,
                session_id=f"{session_id}-denied-transition",
                project_id=project_id,
            ),
            self._arguments_from_schema(by_name[consultation_tool], consultation_type="architecture_review"),
        )
        restricted = self.facade.execute_capability("repository.raw_read", context, {"path": "README.md"}, tool_name="ageix.capabilities.execute")
        placeholder_name = "ageix.validation.scenario.request"
        placeholder = self.facade.execute_tool(placeholder_name, context, {}) if placeholder_name in by_name else None
        audit = self.facade.execute_tool(audit_tool, context, {"limit": 50})
        audit_records = [
            record
            for record in CapabilityAuditService(self.repo_root).list_records()
            if record.get("session_id") == session_id
        ]

        result.responses = {
            "workflow_initial": workflow_initial.model_dump(),
            "identity": identity.model_dump(),
            "proposal": proposal.model_dump(),
            "consultation": consultation.model_dump(),
            "status": status.model_dump(),
            "workflow_final": workflow_final.model_dump(),
            "missing_link_denial": missing_link_denial.model_dump(),
            "restricted_capability_denial": restricted.model_dump(),
            "placeholder_denial": placeholder.model_dump() if placeholder else None,
            "audit": audit.model_dump(),
        }
        capabilities_in_audit = [record.get("capability_id") for record in audit_records]
        result.validation = {
            "discovered_categories": sorted(by_category),
            "schema_consumed": schema_consumed,
            "workflow_hints_consumed": result.consumed_workflow_hints == [consultation_tool, status_tool],
            "workflow_navigation_succeeded": all([workflow_initial.success, proposal.success, consultation.success, status.success]),
            "session_continuity_succeeded": workflow_final.result.get("active_proposal_id") == proposal_id and consultation_id in workflow_final.result.get("active_consultation_ids", []),
            "identity_continuity_succeeded": identity.result.get("client_id") == self.profile.client_id and identity.result.get("provider") == self.profile.provider and identity.result.get("authority_boundary", {}).get("identity_grants_authority") is False,
            "governance_denials_succeeded": missing_link_denial.success is False and restricted.success is False and (placeholder is None or placeholder.success is False),
            "audit_continuity_succeeded": all(item in capabilities_in_audit for item in ["workflow.current", "identity.current", "proposal.submit", "consultation.submit", "proposal.status", "audit.recent"]),
        }
        result.readiness = ClientReadinessService().assess(client_id=self.profile.client_id, validation=result.validation)
        return result

    def _single_tool(self, by_category: dict[str, list[dict[str, Any]]], category: str) -> str:
        tools = by_category.get(category, [])
        if not tools:
            raise LookupError(f"mcp_category_not_discovered:{category}")
        return str(tools[0]["tool_name"])

    def _tool_by_capability(self, tools: list[dict[str, Any]], capability_id: str) -> str:
        for tool in tools:
            if tool.get("capability_id") == capability_id:
                return str(tool["tool_name"])
        raise LookupError(f"mcp_capability_not_discovered:{capability_id}")

    def _first_recommended(self, tool: dict[str, Any], *, category_tools: dict[str, list[dict[str, Any]]], target_capability: str) -> str:
        recommended = list(tool.get("recommended_next_tools") or tool.get("workflow", {}).get("recommended_next_tools") or [])
        by_name = {candidate["tool_name"]: candidate for tools in category_tools.values() for candidate in tools}
        for name in recommended:
            if by_name.get(name, {}).get("capability_id") == target_capability:
                return str(name)
        return self._tool_by_capability([candidate for tools in category_tools.values() for candidate in tools], target_capability)

    def _arguments_from_schema(self, tool: dict[str, Any], **available: Any) -> dict[str, Any]:
        schema = tool.get("input_schema") or {}
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        payload: dict[str, Any] = {}
        for key in required:
            if key in available:
                payload[key] = available[key]
        for key, value in available.items():
            if key in properties:
                payload[key] = value
        return payload
