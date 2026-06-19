from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MCPToolDefinition:
    """Declarative public contract for a governed Ageix MCP tool."""

    name: str
    capability_id: str
    category: str
    description: str
    version: str = "1.0"
    requires_project: bool = True
    requires_auth: bool = True
    enabled: bool = True
    experimental: bool = False
    placeholder: bool = False
    placeholder_reason: str | None = None

    def to_discovery_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.name,
            "name": self.name,
            "capability_id": self.capability_id,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "requires_project": self.requires_project,
            "requires_auth": self.requires_auth,
            "enabled": self.enabled,
            "experimental": self.experimental,
            "placeholder": self.placeholder,
            "placeholder_reason": self.placeholder_reason,
        }


MCP_TOOL_DEFINITIONS: tuple[MCPToolDefinition, ...] = (
    MCPToolDefinition(
        name="ageix.health",
        capability_id="ageix.health",
        category="system",
        description="Return Ageix MCP/capability interface health.",
        requires_project=False,
    ),
    MCPToolDefinition(
        name="ageix.capabilities.list",
        capability_id="capabilities.list",
        category="capability",
        description="List governed Ageix capabilities and MCP tools exposed to external clients.",
        requires_project=False,
    ),
    MCPToolDefinition(
        name="ageix.capabilities.execute",
        capability_id="capabilities.execute",
        category="capability",
        description="Execute a governed Ageix capability by capability ID.",
    ),
    MCPToolDefinition(
        name="ageix.projects.current",
        capability_id="project.current",
        category="project",
        description="Return the explicitly selected current project profile.",
    ),
    MCPToolDefinition(
        name="ageix.projects.profile",
        capability_id="project.profile",
        category="project",
        description="Return a project profile by project ID.",
    ),
    MCPToolDefinition(
        name="ageix.projects.list",
        capability_id="project.list",
        category="project",
        description="List registered Ageix projects visible to the governed interface.",
        requires_project=False,
    ),
    MCPToolDefinition(
        name="ageix.proposals.submit",
        capability_id="proposal.submit",
        category="proposal",
        description="Submit a governed proposal for Chair evaluation.",
    ),
    MCPToolDefinition(
        name="ageix.proposals.get",
        capability_id="proposal.details",
        category="proposal",
        description="Retrieve a governed proposal by ID.",
    ),
    MCPToolDefinition(
        name="ageix.proposals.list",
        capability_id="proposal.list",
        category="proposal",
        description="List governed proposals for a project/session.",
    ),
    MCPToolDefinition(
        name="ageix.proposals.status",
        capability_id="proposal.status",
        category="proposal",
        description="Return the current status for a governed proposal.",
    ),
    MCPToolDefinition(
        name="ageix.consultations.submit",
        capability_id="consultation.submit",
        category="consultation",
        description="Submit external consultation input for a governed proposal.",
    ),
    MCPToolDefinition(
        name="ageix.consultations.get",
        capability_id="consultation.details",
        category="consultation",
        description="Retrieve a submitted consultation by ID.",
    ),
    MCPToolDefinition(
        name="ageix.consultations.list",
        capability_id="consultation.list",
        category="consultation",
        description="List governed consultations.",
    ),
    MCPToolDefinition(
        name="ageix.audit.recent",
        capability_id="audit.recent",
        category="audit",
        description="Return recent scoped audit records.",
    ),
    MCPToolDefinition(
        name="ageix.validation.scenarios.list",
        capability_id="validation.scenarios.list",
        category="validation",
        description="Reserved validation sandbox scenario discovery contract.",
        experimental=True,
        placeholder=True,
        placeholder_reason="validation sandbox not yet implemented",
    ),
    MCPToolDefinition(
        name="ageix.validation.scenario.request",
        capability_id="validation.scenario.request",
        category="validation",
        description="Reserved governed validation sandbox scenario request contract.",
        experimental=True,
        placeholder=True,
        placeholder_reason="validation sandbox not yet implemented",
    ),
    MCPToolDefinition(
        name="ageix.validation.result.get",
        capability_id="validation.result.get",
        category="validation",
        description="Reserved governed validation sandbox result retrieval contract.",
        experimental=True,
        placeholder=True,
        placeholder_reason="validation sandbox not yet implemented",
    ),
)
