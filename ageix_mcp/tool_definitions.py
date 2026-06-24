from __future__ import annotations

from dataclasses import dataclass, field
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
    input_schema: dict[str, Any] = field(default_factory=dict)
    recommended_next_tools: tuple[str, ...] = ()
    related_tools: tuple[str, ...] = ()
    documentation: dict[str, Any] = field(default_factory=dict)

    def to_discovery_dict(self) -> dict[str, Any]:
        workflow = {
            "recommended_next_tools": list(self.recommended_next_tools),
            "related_tools": list(self.related_tools),
        }
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
            "input_schema": self.input_schema or {"type": "object", "properties": {}, "required": []},
            "workflow": workflow,
            "recommended_next_tools": list(self.recommended_next_tools),
            "related_tools": list(self.related_tools),
            "documentation": self.documentation,
        }


def _object_schema(properties: dict[str, dict[str, Any]], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def _string(description: str = "", *, enum: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "string"}
    if description:
        payload["description"] = description
    if enum:
        payload["enum"] = enum
    return payload


def _integer(description: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "integer"}
    if description:
        payload["description"] = description
    return payload


def _array(description: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "array"}
    if description:
        payload["description"] = description
    return payload


def _object(description: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "object"}
    if description:
        payload["description"] = description
    return payload

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
        input_schema=_object_schema({
            "capability_id": _string("Capability ID to execute through governed authorization."),
            "arguments": _object("Capability arguments."),
        }, ["capability_id"]),
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
        input_schema=_object_schema({"project_id": _string("Explicit project ID.")}, ["project_id"]),
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
        input_schema=_object_schema({
            "objective": _string("Proposal objective for Chair evaluation."),
            "proposal_type": _string("Proposal type.", enum=["investigation", "architecture", "implementation", "research"]),
            "parent_proposal_id": _string("Optional parent proposal ID."),
            "proposal_version": _integer("Optional proposal version."),
            "linked_evidence": _array("Linked evidence IDs."),
            "linked_consultations": _array("Linked consultation IDs."),
            "required_consultations": _array("Required consultation types."),
            "conditions": _array("Proposal conditions."),
            "metadata": _object("Additional proposal metadata."),
        }, ["objective"]),
        recommended_next_tools=("ageix.proposals.status", "ageix.consultations.submit"),
        related_tools=("ageix.proposals.get", "ageix.proposals.list"),
    ),
    MCPToolDefinition(
        name="ageix.proposals.get",
        capability_id="proposal.details",
        category="proposal",
        description="Retrieve a governed proposal by ID.",
        input_schema=_object_schema({"proposal_id": _string("Proposal ID to retrieve.")}, ["proposal_id"]),
    ),
    MCPToolDefinition(
        name="ageix.proposals.list",
        capability_id="proposal.list",
        category="proposal",
        description="List governed proposals for a project/session.",
        input_schema=_object_schema({"limit": _integer("Maximum number of proposals to return.")}),
    ),
    MCPToolDefinition(
        name="ageix.proposals.status",
        capability_id="proposal.status",
        category="proposal",
        description="Return the current status for a governed proposal.",
        input_schema=_object_schema({"proposal_id": _string("Proposal ID to check.")}, ["proposal_id"]),
        recommended_next_tools=("ageix.consultations.submit",),
    ),
    MCPToolDefinition(
        name="ageix.consultations.submit",
        capability_id="consultation.submit",
        category="consultation",
        description="Submit external consultation input for a governed proposal.",
        input_schema=_object_schema({
            "proposal_id": _string("Proposal ID receiving consultation evidence."),
            "consultation_type": _string("Consultation type."),
            "summary": _string("Summary or recommendation text."),
            "confidence": {"type": "number", "description": "Confidence from 0.0 to 1.0."},
            "disposition": _string("Consultation disposition."),
            "evidence_sufficient": {"type": "boolean"},
            "findings": _array("Findings."),
            "concerns": _array("Concerns or risks."),
            "recommendations": _array("Suggested improvements."),
            "metadata": _object("Additional consultation metadata."),
        }, ["proposal_id", "consultation_type"]),
        recommended_next_tools=("ageix.consultations.get", "ageix.proposals.status"),
        related_tools=("ageix.consultations.list",),
    ),
    MCPToolDefinition(
        name="ageix.consultations.get",
        capability_id="consultation.details",
        category="consultation",
        description="Retrieve a submitted consultation by ID.",
        input_schema=_object_schema({"consultation_id": _string("Consultation ID to retrieve.")}, ["consultation_id"]),
    ),
    MCPToolDefinition(
        name="ageix.consultations.list",
        capability_id="consultation.list",
        category="consultation",
        description="List governed consultations.",
        input_schema=_object_schema({"limit": _integer("Maximum number of consultations to return.")}),
    ),

    MCPToolDefinition(
        name="ageix.architecture.list",
        capability_id="architecture.list",
        category="architecture",
        description="List governed architecture hierarchy nodes visible to the current project.",
        input_schema=_object_schema({
            "node_type": _string("Optional architecture node type filter.", enum=["project", "domain", "component"]),
            "parent_id": _string("Optional parent architecture ID filter."),
        }),
        recommended_next_tools=("ageix.architecture.details", "ageix.architecture.children"),
        related_tools=("ageix.architecture.subtree",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.details",
        capability_id="architecture.details",
        category="architecture",
        description="Retrieve one governed architecture node by architecture ID or stable path.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path, such as Ageix.MCPPlatform.ToolRegistry."),
        }),
        recommended_next_tools=("ageix.architecture.children", "ageix.architecture.subtree"),
        related_tools=("ageix.architecture.list",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.children",
        capability_id="architecture.children",
        category="architecture",
        description="Retrieve direct children for a governed architecture node.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
            "include_node": {"type": "boolean", "description": "Include the parent node payload."},
        }),
        recommended_next_tools=("ageix.architecture.details", "ageix.architecture.subtree"),
        related_tools=("ageix.architecture.list",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.subtree",
        capability_id="architecture.subtree",
        category="architecture",
        description="Retrieve a governed architecture hierarchy subtree from a node.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
        }),
        recommended_next_tools=("ageix.architecture.details",),
        related_tools=("ageix.architecture.children", "ageix.architecture.list"),
    ),

    MCPToolDefinition(
        name="ageix.architecture.context",
        capability_id="architecture.context",
        category="architecture",
        description="Build summary-first architecture context for a governed architecture node without repository-wide discovery.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
            "include_detail": {"type": "boolean", "description": "Include detailed node and approved description payloads."},
        }),
        recommended_next_tools=("ageix.architecture.details", "ageix.evidence.package.details"),
        related_tools=("ageix.architecture.children", "ageix.architecture.subtree", "ageix.decision.trace.details"),
    ),

    MCPToolDefinition(
        name="ageix.architecture.health",
        capability_id="architecture.health",
        category="architecture",
        description="Return deterministic architecture health indicators for one governed architecture node.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
        }),
        recommended_next_tools=("ageix.architecture.coverage", "ageix.architecture.context"),
        related_tools=("ageix.architecture.details", "ageix.evidence.package.summary"),
    ),
    MCPToolDefinition(
        name="ageix.architecture.coverage",
        capability_id="architecture.coverage",
        category="architecture",
        description="Return deterministic architecture coverage metrics for a project registry baseline.",
        input_schema=_object_schema({
            "project_id": _string("Explicit project ID."),
        }, ["project_id"]),
        recommended_next_tools=("ageix.architecture.health", "ageix.architecture.list"),
        related_tools=("ageix.architecture.subtree",),
    ),


    MCPToolDefinition(
        name="ageix.architecture.review.submit",
        capability_id="architecture.review.submit",
        category="architecture",
        description="Submit a governed architecture review from an authorized architect MCP partner.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
            "summary": _string("Review summary."),
            "rationale": _string("Review rationale."),
            "no_findings": {"type": "boolean", "description": "True when the review found no concerns."},
            "metadata": _object("Additional review metadata."),
        }),
        recommended_next_tools=("ageix.architecture.finding.submit", "ageix.architecture.review.get"),
        related_tools=("ageix.architecture.review.list", "ageix.architecture.health"),
    ),
    MCPToolDefinition(
        name="ageix.architecture.review.get",
        capability_id="architecture.review.get",
        category="architecture",
        description="Retrieve a governed architecture review by review ID.",
        input_schema=_object_schema({"review_id": _string("Architecture review ID.")}, ["review_id"]),
        related_tools=("ageix.architecture.review.list",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.review.list",
        capability_id="architecture.review.list",
        category="architecture",
        description="List governed architecture reviews for a project or architecture node.",
        input_schema=_object_schema({
            "project_id": _string("Explicit project ID."),
            "architecture_id": _string("Optional architecture node ID."),
            "limit": _integer("Maximum reviews to return."),
        }),
        related_tools=("ageix.architecture.review.get",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.finding.submit",
        capability_id="architecture.finding.submit",
        category="architecture",
        description="Submit a structured architecture finding from an authorized architect MCP partner.",
        input_schema=_object_schema({
            "review_id": _string("Optional architecture review ID."),
            "architecture_id": _string("Single affected architecture node ID."),
            "path": _string("Single affected stable architecture path."),
            "affected_architecture_ids": _array("Affected architecture IDs or paths."),
            "severity": _string("Finding severity.", enum=["informational", "concern", "significant_concern", "critical_concern"]),
            "category": _string("Finding category.", enum=["documentation_gap", "evidence_gap", "decision_gap", "architecture_inconsistency", "architecture_staleness", "coverage_gap", "intent_miss", "requires_additional_discovery", "other"]),
            "summary": _string("Finding summary."),
            "rationale": _string("Finding rationale."),
            "other_explanation": _string("Required when category is other."),
            "metadata": _object("Additional finding metadata."),
        }, ["summary"]),
        recommended_next_tools=("ageix.architecture.challenge.submit", "ageix.architecture.review.get"),
        related_tools=("ageix.architecture.health",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.challenge.submit",
        capability_id="architecture.challenge.submit",
        category="architecture",
        description="Submit an architecture challenge with context and intent.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
            "finding_id": _string("Optional finding ID that prompted the challenge."),
            "challenge_summary": _string("Challenge summary."),
            "context": _string("Architectural context for the disagreement."),
            "intent": _string("Architectural intent behind the challenge."),
            "rationale": _string("Challenge rationale."),
            "proposed_direction": _string("Optional proposed direction."),
            "metadata": _object("Additional challenge metadata."),
        }, ["challenge_summary", "context", "intent"]),
        recommended_next_tools=("ageix.architecture.revision.propose", "ageix.architecture.challenge.get"),
        related_tools=("ageix.architecture.challenge.list",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.challenge.get",
        capability_id="architecture.challenge.get",
        category="architecture",
        description="Retrieve a governed architecture challenge by challenge ID.",
        input_schema=_object_schema({"challenge_id": _string("Architecture challenge ID.")}, ["challenge_id"]),
        related_tools=("ageix.architecture.challenge.list",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.challenge.list",
        capability_id="architecture.challenge.list",
        category="architecture",
        description="List governed architecture challenges for a project or architecture node.",
        input_schema=_object_schema({
            "project_id": _string("Explicit project ID."),
            "architecture_id": _string("Optional architecture node ID."),
            "limit": _integer("Maximum challenges to return."),
        }),
        related_tools=("ageix.architecture.challenge.get",),
    ),
    MCPToolDefinition(
        name="ageix.architecture.revision.propose",
        capability_id="architecture.revision.propose",
        category="architecture",
        description="Propose a governed architecture registry revision through the existing proposal system; does not mutate the registry directly.",
        input_schema=_object_schema({
            "architecture_id": _string("Architecture node ID."),
            "path": _string("Stable architecture path."),
            "challenge_id": _string("Optional challenge ID."),
            "objective": _string("Revision objective for Chair governance."),
            "proposed_changes": _object("Allowed architecture-registry-only change set."),
            "metadata": _object("Additional revision proposal metadata."),
        }, ["objective", "proposed_changes"]),
        recommended_next_tools=("ageix.proposals.status", "ageix.proposals.get"),
        related_tools=("ageix.architecture.challenge.get", "ageix.proposals.list"),
    ),

    MCPToolDefinition(
        name="ageix.workflow.current",
        capability_id="workflow.current",
        category="workflow",
        description="Return advisory workflow/session state for the current governed MCP session.",
        input_schema=_object_schema({}),
        recommended_next_tools=("ageix.proposals.submit", "ageix.consultations.submit", "ageix.proposals.status"),
    ),
    MCPToolDefinition(
        name="ageix.identity.current",
        capability_id="identity.current",
        category="identity",
        description="Return resolved MCP caller identity and governance profile for the current request context.",
        requires_project=True,
        input_schema=_object_schema({}),
        related_tools=("ageix.workflow.current",),
    ),
    MCPToolDefinition(
        name="ageix.audit.recent",
        capability_id="audit.recent",
        category="audit",
        description="Return recent scoped audit records.",
        input_schema=_object_schema({"limit": _integer("Maximum number of audit records to return.")}),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.list",
        capability_id="evidence.package.list",
        category="evidence",
        description="List project-scoped immutable evidence package summaries with pagination and filters.",
        input_schema=_object_schema({
            "limit": _integer("Maximum package summaries to return."),
            "offset": _integer("Zero-based pagination offset."),
            "proposal_id": _string("Optional proposal ID filter."),
            "evidence_plan_id": _string("Optional evidence plan ID filter."),
            "stale": {"type": "boolean", "description": "Optional stale/fresh filter."},
            "objective_contains": _string("Case-insensitive objective contains filter."),
            "context_contains": _string("Case-insensitive package context contains filter."),
            "created_before": _string("Optional ISO timestamp upper bound."),
            "created_after": _string("Optional ISO timestamp lower bound."),
        }),
        recommended_next_tools=("ageix.evidence.package.details", "ageix.evidence.package.freshness", "ageix.evidence.package.retrieve"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.search",
        capability_id="evidence.package.search",
        category="evidence",
        description="Search project-scoped immutable evidence package summaries without returning package contents.",
        input_schema=_object_schema({
            "query": _string("Search text matched against package objective/context."),
            "limit": _integer("Maximum package summaries to return."),
            "offset": _integer("Zero-based pagination offset."),
            "proposal_id": _string("Optional proposal ID filter."),
            "evidence_plan_id": _string("Optional evidence plan ID filter."),
            "stale": {"type": "boolean", "description": "Optional stale/fresh filter."},
            "objective_contains": _string("Case-insensitive objective contains filter."),
            "context_contains": _string("Case-insensitive package context contains filter."),
        }),
        recommended_next_tools=("ageix.evidence.package.details", "ageix.evidence.package.retrieve", "ageix.evidence.package.recommend"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.details",
        capability_id="evidence.package.details",
        category="evidence",
        description="Inspect package metadata, freshness, counts, and provenance manifest without returning package contents.",
        input_schema=_object_schema({"package_id": _string("Evidence package ID.")}, ["package_id"]),
        related_tools=("ageix.evidence.package.retrieve", "ageix.evidence.package.freshness"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.freshness",
        capability_id="evidence.package.freshness",
        category="evidence",
        description="Evaluate current repository content freshness for one evidence package and update the index.",
        input_schema=_object_schema({"package_id": _string("Evidence package ID.")}, ["package_id"]),
        related_tools=("ageix.evidence.package.details",),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.rehydrate",
        capability_id="evidence.package.rehydrate",
        category="evidence",
        description="Legacy alias: return one immutable historical evidence package by package ID without freshness evaluation.",
        input_schema=_object_schema({"package_id": _string("Evidence package ID.")}, ["package_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.freshness"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.retrieve",
        capability_id="evidence.package.retrieve",
        category="evidence",
        description="Retrieve immutable historical evidence package contents after an explicit package request.",
        input_schema=_object_schema({"package_id": _string("Evidence package ID.")}, ["package_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.freshness"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.recommend",
        capability_id="evidence.package.recommend",
        category="evidence",
        description="Recommend visible historical evidence packages for a new objective; advisory to Chair only.",
        input_schema=_object_schema({
            "objective": _string("Objective to compare against visible package history."),
            "limit": _integer("Maximum recommendations to return."),
            "min_similarity": {"type": "number", "description": "Minimum deterministic similarity threshold."},
        }, ["objective"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.reuse"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.reuse",
        capability_id="evidence.package.reuse",
        category="evidence",
        description="Create a new immutable child package that records Chair-approved reuse of a visible parent package.",
        input_schema=_object_schema({
            "package_id": _string("Parent evidence package ID."),
            "objective": _string("Optional child package objective."),
            "lineage_type": _string("Lineage type.", enum=["reuse", "refresh", "expansion", "derived"]),
            "reuse_reason": _string("Chair reuse decision rationale."),
        }, ["package_id"]),
        related_tools=("ageix.evidence.package.lineage", "ageix.evidence.package.details"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.deprecate",
        capability_id="evidence.package.deprecate",
        category="evidence",
        description="Mark a visible package deprecated in catalog metadata without mutating package contents.",
        input_schema=_object_schema({
            "package_id": _string("Evidence package ID."),
            "reason": _string("Governance deprecation rationale."),
        }, ["package_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.recommend"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.supersede",
        capability_id="evidence.package.supersede",
        category="evidence",
        description="Mark a visible package superseded by a newer compatible package without mutating package contents.",
        input_schema=_object_schema({
            "package_id": _string("Evidence package ID being superseded."),
            "superseded_by_package_id": _string("Newer replacement evidence package ID."),
            "reason": _string("Governance supersession rationale."),
        }, ["package_id", "superseded_by_package_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.recommend"),
    ),
    MCPToolDefinition(
        name="ageix.evidence.package.lineage",
        capability_id="evidence.package.lineage",
        category="evidence",
        description="Return visible parent, child, ancestor, and descendant package lineage.",
        input_schema=_object_schema({"package_id": _string("Evidence package ID.")}, ["package_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.retrieve"),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.create",
        capability_id="decision.trace.create",
        category="decision_trace",
        description="Internal Chair-only decision trace creation capability; not exposed as an enabled MCP tool.",
        enabled=False,
        input_schema=_object_schema({
            "decision_summary": _string("Decision summary."),
            "outcome": _string("Decision outcome.", enum=["approved", "rejected", "implemented", "superseded", "abandoned", "deferred", "backlog"]),
            "decision_id": _string("Optional external decision ID."),
            "decision_type": _string("Decision type."),
            "proposal_id": _string("Linked proposal ID."),
            "evidence_package_ids": _array("Linked evidence package IDs."),
            "consultation_ids": _array("Linked consultation IDs."),
            "validation_ids": _array("Linked validation IDs."),
            "repository_snapshot": _object("Repository snapshot metadata."),
            "reason": _string("Decision rationale."),
            "outcome_metadata": _object("Future outcome hook metadata such as backlog/deferred details."),
            "related_entities": _object("Extensible related entity IDs for future architecture links."),
            "metadata": _object("Additional trace metadata."),
        }, ["decision_summary", "outcome"]),
        related_tools=("ageix.decision.trace.get", "ageix.decision.trace.list"),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.get",
        capability_id="decision.trace.get",
        category="decision_trace",
        description="Legacy alias: retrieve one append-only decision trace with linked package summaries and current freshness awareness.",
        input_schema=_object_schema({
            "trace_id": _string("Decision trace ID."),
            "include_freshness": {"type": "boolean", "description": "Include current package freshness indicators."},
        }, ["trace_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.freshness"),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.details",
        capability_id="decision.trace.details",
        category="decision_trace",
        description="Retrieve one append-only decision trace with linked package summaries and current freshness awareness.",
        input_schema=_object_schema({
            "trace_id": _string("Decision trace ID."),
            "include_freshness": {"type": "boolean", "description": "Include current package freshness indicators."},
        }, ["trace_id"]),
        related_tools=("ageix.evidence.package.details", "ageix.evidence.package.freshness"),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.list",
        capability_id="decision.trace.list",
        category="decision_trace",
        description="List project-scoped decision traces by proposal, package, outcome, or summary text.",
        input_schema=_object_schema({
            "limit": _integer("Maximum traces to return."),
            "offset": _integer("Zero-based pagination offset."),
            "decision_id": _string("Decision ID filter."),
            "proposal_id": _string("Proposal ID filter."),
            "evidence_package_id": _string("Evidence package ID filter."),
            "outcome": _string("Outcome filter.", enum=["approved", "rejected", "implemented", "superseded", "abandoned", "deferred", "backlog"]),
            "summary_contains": _string("Case-insensitive decision summary contains filter."),
        }),
        related_tools=("ageix.decision.trace.get",),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.search",
        capability_id="decision.trace.search",
        category="decision_trace",
        description="Search project-scoped decision traces by query, proposal, package, outcome, or summary text.",
        input_schema=_object_schema({
            "query": _string("Search text matched against decision summary."),
            "limit": _integer("Maximum traces to return."),
            "offset": _integer("Zero-based pagination offset."),
            "decision_id": _string("Decision ID filter."),
            "proposal_id": _string("Proposal ID filter."),
            "evidence_package_id": _string("Evidence package ID filter."),
            "outcome": _string("Outcome filter.", enum=["approved", "rejected", "implemented", "superseded", "abandoned", "deferred", "backlog"]),
            "summary_contains": _string("Case-insensitive decision summary contains filter."),
        }),
        related_tools=("ageix.decision.trace.details",),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.history",
        capability_id="decision.trace.history",
        category="decision_trace",
        description="Find historical decision traces related to a package, proposal, or decision ID.",
        input_schema=_object_schema({
            "package_id": _string("Evidence package ID filter."),
            "proposal_id": _string("Proposal ID filter."),
            "decision_id": _string("Decision ID filter."),
            "limit": _integer("Maximum traces to return."),
            "offset": _integer("Zero-based pagination offset."),
        }),
        related_tools=("ageix.decision.trace.details", "ageix.evidence.package.details"),
    ),
    MCPToolDefinition(
        name="ageix.decision.trace.package_history",
        capability_id="decision.trace.package_history",
        category="decision_trace",
        description="Legacy alias: find decision traces that used a specific evidence package.",
        input_schema=_object_schema({"package_id": _string("Evidence package ID.")}, ["package_id"]),
        related_tools=("ageix.decision.trace.get", "ageix.evidence.package.details"),
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
        input_schema=_object_schema({"scenario": _string("Validation scenario identifier.")}),
        recommended_next_tools=("ageix.validation.result.get",),
    ),
    MCPToolDefinition(
        name="ageix.validation.result.get",
        capability_id="validation.result.get",
        category="validation",
        description="Reserved governed validation sandbox result retrieval contract.",
        experimental=True,
        placeholder=True,
        placeholder_reason="validation sandbox not yet implemented",
        input_schema=_object_schema({"result_id": _string("Validation result identifier.")}, ["result_id"]),
    ),
)
