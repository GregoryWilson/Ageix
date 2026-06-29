from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.architecture import ArchitectureDescriptionState, ArchitectureNode, ArchitectureNodeType
from models.architecture_decision_record import ArchitectureDecisionRecord, ArchitectureDecisionRecordStatus
from models.architecture_guidance import ArchitectureGuidanceStatus, ArchitectureIntent, ArchitecturePrinciple
from services.architecture_guidance_context_service import ArchitectureGuidanceContextService
from services.architecture_registry_service import ArchitectureRegistryService
from services.architecture_work_context_service import ArchitectureWorkContextService


class AgeixArchitectureBaselineService:
    """Populate and validate the canonical Ageix self-architecture baseline.

    Sprint 18.10 deliberately treats Ageix architecture as seed content consumed by
    the architecture platform, not as hard-coded behavior in retrieval services.
    """

    PROJECT_ID = "Ageix"
    VERSION = "18.10"

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = ArchitectureRegistryService(self.repo_root)
        self.guidance_context = ArchitectureGuidanceContextService(self.repo_root)
        self.work_context = ArchitectureWorkContextService(self.repo_root)
        self.arch_root = self.repo_root / ".ageix" / "architecture"
        self.adr_root = self.arch_root / "adrs"
        self.principle_root = self.arch_root / "guidance" / "principles"
        self.intent_root = self.arch_root / "guidance" / "intents"

    def populate(self, *, include_review: bool = True) -> dict[str, Any]:
        before_ids = {item["architecture_id"] for item in self.registry.list_nodes(project_id=self.PROJECT_ID).get("nodes", [])}
        node_map = self._populate_nodes()
        principle_ids = self._populate_principles(node_map)
        intent_ids = self._populate_intents(node_map, principle_ids)
        adr_ids = self._populate_adrs(node_map)
        self._link_guidance_to_adrs(principle_ids, intent_ids, adr_ids)
        review = self._ensure_baseline_review(node_map["Ageix"]) if include_review else None
        validation = self.validate()
        after = self.registry.list_nodes(project_id=self.PROJECT_ID).get("nodes", [])
        after_ids = {item["architecture_id"] for item in after}
        return {
            "project_id": self.PROJECT_ID,
            "baseline_version": self.VERSION,
            "created_node_count": len(after_ids - before_ids),
            "total_node_count": len(after),
            "domain_count": len([n for n in after if n.get("node_type") == "domain"]),
            "component_count": len([n for n in after if n.get("node_type") == "component"]),
            "service_count": len([n for n in after if n.get("node_type") == "service"]),
            "principle_count": len(principle_ids),
            "intent_count": len(intent_ids),
            "adr_count": len(adr_ids),
            "review_id": review.get("review_id") if review else None,
            "validation": validation,
            "deterministic_seed": True,
            "content_population_only": True,
        }

    def validate(self) -> dict[str, Any]:
        nodes = self.registry.list_nodes(project_id=self.PROJECT_ID).get("nodes", [])
        paths = {str(item.get("path") or "") for item in nodes}
        required_paths = {
            "Ageix",
            "Ageix.GovernancePlatform",
            "Ageix.WorkerPlatform.Chair",
            "Ageix.WorkerPlatform.Planner",
            "Ageix.WorkerPlatform.Router",
            "Ageix.EvidencePlatform.EvidenceBroker",
            "Ageix.ArchitecturePlatform.GuidanceContext",
            "Ageix.ArchitecturePlatform.WorkContext",
            "Ageix.MCPPlatform.CapabilityRegistry",
            "Ageix.SecurityPlatform.OAuthJWTIdentity",
            "Ageix.SessionPlatform.SessionState",
            "Ageix.ValidationPlatform.ValidationAgent",
        }
        missing = sorted(required_paths - paths)
        principle_count = len(self._load_seed_files(self.principle_root))
        intent_count = len(self._load_seed_files(self.intent_root))
        adr_count = len(self._load_seed_files(self.adr_root))
        service_nodes = [item for item in nodes if item.get("node_type") == "service"]
        service_description_gaps = []
        for item in service_nodes:
            node = self.registry.require_node(str(item.get("architecture_id")))
            if len([part for part in node.description.split(".") if part.strip()]) < 2:
                service_description_gaps.append(node.path)
        coverage = self.registry.get_coverage(project_id=self.PROJECT_ID).model_dump(mode="json")
        return {
            "project_id": self.PROJECT_ID,
            "baseline_version": self.VERSION,
            "valid": not missing and principle_count >= 6 and intent_count >= 5 and adr_count >= 12 and not service_description_gaps,
            "missing_required_paths": missing,
            "principle_count": principle_count,
            "intent_count": intent_count,
            "adr_count": adr_count,
            "service_count": len(service_nodes),
            "service_description_gaps": service_description_gaps,
            "coverage": coverage,
            "deterministic": True,
            "no_architecture_quality_scoring": True,
        }

    def retrieval_probe(self) -> dict[str, Any]:
        evidence = self.registry.require_node("Ageix.EvidencePlatform.EvidenceBroker")
        mcp_discovery = self.registry.require_node("Ageix.MCPPlatform.Discovery")
        guidance = self.guidance_context.build_context_package(project_id=self.PROJECT_ID, architecture_id=evidence.architecture_id, persist=False)
        work = self.work_context.build_work_context_package(
            project_id=self.PROJECT_ID,
            architecture_id=mcp_discovery.architecture_id,
            work_summary="Modify MCP discovery behavior.",
            persist=False,
        )
        return {
            "guidance_probe": {
                "architecture_id": guidance.architecture_id,
                "principle_count": len(guidance.governing_principles),
                "intent_count": len(guidance.active_intent),
                "adr_count": len(guidance.decision_context),
                "brief_summary": guidance.brief_summary,
            },
            "work_context_probe": {
                "work_context_id": work.work_context_id,
                "resolved_node_count": len(work.resolved_architecture_nodes),
                "impacted_node_count": len(work.impacted_nodes),
                "guidance_package_count": work.guidance_context.get("package_count"),
                "summary_first": True,
            },
            "retrieval_usable": len(guidance.governing_principles) > 0 and len(work.resolved_architecture_nodes) == 1,
        }

    def _populate_nodes(self) -> dict[str, ArchitectureNode]:
        nodes: dict[str, ArchitectureNode] = {}

        project = self._ensure_node(
            key="Ageix",
            architecture_id="ARCH-AGEIX-PROJECT",
            name="Ageix",
            node_key="Ageix",
            path="Ageix",
            node_type="project",
            description="Ageix is a local-first governed AI gateway for safe multi-agent software work. It coordinates proposals, evidence, architecture context, validation, MCP exposure, and external model collaboration while preserving human authority and deterministic governance boundaries.",
            metadata={"purpose": "Canonical self-architecture root for the Ageix project."},
        )
        nodes["Ageix"] = project

        domains = {
            "GovernancePlatform": ("Governance Platform", "Owns proposal lifecycle, consultation governance, decision traceability, approval controls, and Chair authority. It is the policy and authority layer that prevents workers or external agents from bypassing governed process."),
            "WorkerPlatform": ("Worker Platform", "Coordinates future execution-oriented actors such as Chair, Planner, Router, Validation Worker, and future specialized workers. In Phase 18 it is documented as architecture, not granted autonomous execution authority."),
            "EvidencePlatform": ("Evidence Platform", "Plans, retrieves, packages, refreshes, and reuses evidence for governed decisions. It is the factual context system that supports proposals, validation, architecture traceability, and MCP consumers."),
            "ArchitecturePlatform": ("Architecture Platform", "Maintains architecture registry, hierarchy, relationships, reviews, ADRs, principles, intent, guidance, guidance context, and work context. It is the design-truth layer for Ageix."),
            "MCPPlatform": ("MCP Platform", "Exposes governed Ageix capabilities to external model clients through discoverable, permissioned, summary-first tools. It preserves governance while enabling ChatGPT and future clients to retrieve and execute approved capabilities."),
            "SecurityPlatform": ("Security Platform", "Provides authentication, authorization, trust boundaries, client controls, capability security, OAuth/JWT validation, and abuse hardening. It assumes trusted clients can still misuse access and therefore defends at multiple layers."),
            "SessionPlatform": ("Session Platform", "Maintains identity, session state, workflow context, and continuity across governed interactions. It lets stateless external agents participate without being allowed to self-assert authority."),
            "ValidationPlatform": ("Validation Platform", "Executes approved validation profiles and collects validation evidence without direct repo mutation. It supports smoke tests, readiness checks, and future validation sandbox maturity."),
            "WebPlatform": ("Web Platform", "Hosts HTTP APIs, routes, request context, health checks, and the web-facing boundary for Ageix. It connects authenticated transport to governed capability execution."),
            "InfrastructurePlatform": ("Infrastructure Platform", "Provides runtime, storage, configuration, deployment, TLS, DNS, reverse proxy, and operational environment boundaries. It keeps local-first operation practical while allowing controlled public exposure."),
        }
        for key, (name, desc) in domains.items():
            nodes[key] = self._ensure_node(
                key=key,
                architecture_id=f"ARCH-AGEIX-{key.upper()}",
                name=name,
                node_key=key,
                path=f"Ageix.{key}",
                node_type="domain",
                parent_id=project.architecture_id,
                description=desc,
            )

        components = {
            "GovernancePlatform": [
                ("ProposalSystem", "Proposal System", "Captures proposed changes as governed artifacts before execution. It tracks objective, evidence links, session context, status, and Chair decision flow."),
                ("ConsultationFramework", "Consultation Framework", "Coordinates advisory input from external or local participants. It supports confidence-building without allowing advisors to directly mutate repo state."),
                ("DecisionTrace", "Decision Trace", "Records historical decision lineage for approved and rejected governed actions. It lets Ageix explain why a decision happened later."),
                ("GovernancePolicy", "Governance Policy", "Defines approval thresholds, trust budgets, authority boundaries, and policy metadata. It preserves the principle that governance comes before execution."),
            ],
            "WorkerPlatform": [
                ("Chair", "Chair", "Acts as the governed authority and decision coordinator for proposal evaluation. Chair preserves human authority and prevents worker bypass."),
                ("Planner", "Planner", "Builds deterministic work packets and staged plans from approved objectives. It prepares work without granting uncontrolled repository mutation."),
                ("Router", "Router", "Routes requests to appropriate capabilities, participants, or worker roles based on context and policy. It keeps execution paths explicit and auditable."),
                ("ValidationWorker", "Validation Worker", "Runs approved validation profiles and reports outcomes. It is intentionally limited to validation and evidence collection."),
                ("FutureWorkers", "Future Workers", "Placeholder architecture component for future TaskWorker, ArchitectWorker, DevWorker, and voice/automation roles. Future workers must consume governed context instead of inferring authority."),
            ],
            "EvidencePlatform": [
                ("EvidenceBroker", "Evidence Broker", "Turns evidence intent into governed evidence plans and packages. It controls what may be retrieved and prevents broad repo walks."),
                ("EvidencePackages", "Evidence Packages", "Stores immutable evidence snapshots with provenance, freshness, summaries, and traceability. Packages are reusable decision context rather than transient retrieval results."),
                ("FreshnessEvaluation", "Freshness Evaluation", "Determines whether evidence has become stale relative to source changes and policy windows. It protects decisions from unknowingly relying on outdated context."),
                ("ReuseLineage", "Reuse and Lineage", "Tracks evidence package reuse, parent/child package relationships, and historical evidence continuity. It reduces repeated collection while preserving traceability."),
                ("MCPEvidenceAccess", "MCP Evidence Access", "Exposes summary-first evidence discovery and governed package retrieval to external MCP consumers. It keeps access read-only and scoped."),
            ],
            "ArchitecturePlatform": [
                ("ArchitectureRegistry", "Architecture Registry", "Stores first-class architecture nodes and metadata. It is the system of record for project, domain, component, and service architecture."),
                ("ArchitectureHierarchy", "Architecture Hierarchy", "Maintains parent-child architecture structure from project through service. It lets Ageix reason about where work belongs without reading the whole repository."),
                ("ArchitectureRelationships", "Architecture Relationships", "Captures dependency, consumer, provider, and governance relationships between architecture nodes. It powers deterministic work impact visibility."),
                ("ArchitectureContext", "Architecture Context", "Builds summary-first context for architecture nodes. It gives humans and MCP consumers useful architectural context without large payloads."),
                ("ArchitectureReviews", "Architecture Reviews", "Records architecture review submissions, findings, challenges, and revision proposals. It supports cautious completeness review rather than automated scoring."),
                ("ArchitectureADRs", "Architecture ADRs", "Stores architecture decision records and historical decision rationale. ADRs explain why the current baseline exists."),
                ("ArchitectureGuidance", "Architecture Guidance", "Derives guidance from accepted principles and intent. It makes future work aware of what must be preserved."),
                ("GuidanceContext", "Guidance Context", "Packages effective inherited guidance into immutable or on-demand GUIDECTX artifacts. It is the bridge from architecture guidance to consumers."),
                ("WorkContext", "Work Context", "Packages architecture scope, guidance, and direct impact visibility into WORKCTX artifacts. It is the bridge from architecture to future workers."),
            ],
            "MCPPlatform": [
                ("CapabilityRegistry", "Capability Registry", "Registers governed capabilities and metadata for external discovery. It separates capability discovery from direct authority."),
                ("Discovery", "Discovery", "Returns summary-first capability lists with filtering and pagination. It keeps growing MCP catalogs usable for external clients."),
                ("FacadeExecution", "Facade Execution", "Routes MCP tool execution through governance-preserving capability handlers. It prevents external agents from bypassing Ageix service boundaries."),
                ("TransportBridge", "Transport Bridge", "Provides the MCP transport endpoint and bridges protocol requests into Ageix capability execution. It is the public integration boundary for model clients."),
                ("ExternalAgentAccess", "External Agent Access", "Manages external agent-facing tool schemas, workflow hints, related tools, and discoverability. It keeps external model interaction structured and auditable."),
            ],
            "SecurityPlatform": [
                ("OAuthJWTIdentity", "OAuth/JWT Identity", "Validates OAuth-issued JWTs through issuer metadata and JWKS. It prevents client self-assertion and binds identity to tokens."),
                ("Authorization", "Authorization", "Maps identity, scopes, projects, and capability metadata into execution authorization. It gates capability use after authentication succeeds."),
                ("TrustBoundaries", "Trust Boundaries", "Defines and enforces boundaries between external agents, MCP, repository access, and governed services. It assumes every boundary needs explicit controls."),
                ("ClientAdmission", "Client Admission", "Allows, denies, or placeholders client identities and model providers. It includes denylist behavior such as permanent Grok denial."),
                ("CapabilitySecurity", "Capability Security", "Protects individual capability execution with access levels, governance metadata, and repository-access restrictions. It ensures discovery never grants authority."),
            ],
            "SessionPlatform": [
                ("Identity", "Identity", "Represents current authenticated agent, client, project, and authority context. It is token-derived, not header-derived."),
                ("SessionState", "Session State", "Carries session continuity across MCP and internal calls. It supports stateless clients while preserving workflow history."),
                ("WorkflowContext", "Workflow Context", "Tracks current proposal, consultation, decision, and execution workflow context. It lets related tools understand where a request fits."),
                ("Persistence", "Persistence", "Stores session and workflow records needed for continuity and audit. It avoids relying on model memory for governed state."),
                ("SharedConversation", "Shared Conversation", "Hosts governed multi-agent conversations between claude.ai, Claude Code, Lex, and the Ageix Chair. It enforces rules of engagement, turn-taking, and directed-question obligations rather than letting agents free-talk."),
            ],
            "ValidationPlatform": [
                ("ValidationAgent", "Validation Agent", "Runs approved validation profiles and returns deterministic results. It cannot directly write repo changes or bypass governance."),
                ("ValidationProfiles", "Validation Profiles", "Defines allowed validation commands and profiles. Profiles make test execution explicit and auditable."),
                ("SmokeEvidence", "Smoke Evidence", "Captures short-lived smoke validation evidence and cleanup rules. It supports immediate validation without polluting long-term history."),
                ("ReadinessValidation", "Readiness Validation", "Checks exposure, TLS, reputation, MCP readiness, and operational deployment assumptions. It helps keep public integration safe."),
            ],
            "WebPlatform": [
                ("APILayer", "API Layer", "Hosts FastAPI application surfaces for health, MCP, auth, and internal routes. It is the HTTP entry point for Ageix services."),
                ("Routes", "Routes", "Maps web requests to service calls and capability adapters. Routes should remain thin and governance-aware."),
                ("RequestContext", "Request Context", "Builds authenticated request context from token and transport metadata. It supplies services with identity without trusting caller headers."),
            ],
            "InfrastructurePlatform": [
                ("Storage", "Storage", "Persists architecture, evidence, proposals, traces, and package artifacts under governed project storage. It favors transparent files and indexes over opaque hidden state."),
                ("Configuration", "Configuration", "Stores runtime controls, auth settings, exposure policies, and validation configuration. It keeps environment-specific behavior explicit."),
                ("Runtime", "Runtime", "Runs Ageix under local VM, Python, FastAPI, Uvicorn, and supporting services. It keeps the project local-first while supporting public endpoints."),
                ("Deployment", "Deployment", "Manages DNS, TLS, nginx, Keycloak, and public-facing deployment topology. It turns local-first services into controlled external integration points."),
            ],
        }
        component_nodes: dict[str, ArchitectureNode] = {}
        for domain_key, rows in components.items():
            for comp_key, name, desc in rows:
                component = self._ensure_node(
                    key=comp_key,
                    architecture_id=f"ARCH-AGEIX-{domain_key.upper()}-{comp_key.upper()}",
                    name=name,
                    node_key=comp_key,
                    path=f"Ageix.{domain_key}.{comp_key}",
                    node_type="component",
                    parent_id=nodes[domain_key].architecture_id,
                    description=desc,
                    metadata={"service_summaries": []},
                )
                component_nodes[comp_key] = component
                nodes[comp_key] = component

        services = {
            "ProposalSystem": ["ProposalService:Creates and stores governed proposals before work is executed. It preserves objective, session, agent, evidence links, and proposal status so downstream decision trace and Chair review have stable context.", "ProposalStatusService:Provides status-oriented retrieval for proposal lifecycle checks. It helps MCP consumers and workers understand whether a proposal is pending, approved, rejected, or otherwise actionable."],
            "ConsultationFramework": ["ConsultationSessionService:Maintains consultation sessions and participant context. It allows advisory models or humans to contribute without granting them direct repository authority.", "ConsultationResultAggregator:Aggregates advisor responses into structured findings, confidence, concerns, and recommendations. It supports Chair evaluation while keeping consultation output separate from decisions."],
            "DecisionTrace": ["DecisionTraceService:Records durable trace events for governed decisions. It links decisions back to proposals, evidence, and architecture context for later explanation."],
            "GovernancePolicy": ["CapabilityExecutionService:Applies capability metadata, authorization, and governance boundaries before tool handlers execute. It is a core enforcement point between discovery and actual action."],
            "Chair": ["ChairDecisionService:Represents the authority boundary where governed proposals are evaluated. It protects Ageix from workers assuming approval or bypassing human governance."],
            "Planner": ["PlannerAgent:Builds structured plans and work packets from objectives. It should consume architecture context and evidence rather than guessing system intent."],
            "Router": ["RoutingService:Selects target capabilities, participants, or worker paths based on explicit context. It exists to keep routing decisions auditable and policy-aware."],
            "ValidationWorker": ["ValidationAgentService:Executes approved validation profiles and returns results. It collects evidence of correctness without direct mutation authority."],
            "EvidenceBroker": ["EvidenceBrokerService:Coordinates evidence intent, planning, approval, retrieval, and packaging. It prevents broad repository walks by forcing evidence requests through explicit plans.", "EvidencePlanningService:Builds constrained evidence plans from intent. It explains why evidence is needed and what scope is allowed before retrieval."],
            "EvidencePackages": ["EvidencePackageService:Creates immutable evidence packages from approved evidence acquisition. It is the main boundary between evidence collection and reusable decision context."],
            "FreshnessEvaluation": ["EvidenceFreshnessService:Evaluates whether an evidence package remains current. It compares source state and configured freshness rules so stale evidence can be surfaced."],
            "ReuseLineage": ["EvidenceReuseService:Tracks package reuse and lineage. It lets Ageix avoid duplicate evidence collection while preserving historical context."],
            "MCPEvidenceAccess": ["MCPEvidenceAccessService:Exposes evidence search, summary-first retrieval, and explicit package access to external MCP consumers. It keeps evidence access governed and read-only."],
            "ArchitectureRegistry": ["ArchitectureRegistryService:Stores and retrieves architecture nodes, health, reviews, findings, and challenges. It is the architecture system of record for Ageix."],
            "ArchitectureHierarchy": ["ArchitectureHierarchyService:Represents the project-domain-component-service tree. It helps future workers resolve where a change belongs."],
            "ArchitectureRelationships": ["ArchitectureRelationshipResolver:Reads metadata relationships and hierarchy links for deterministic impact visibility. It avoids semantic guessing while still exposing dependencies and consumers."],
            "ArchitectureContext": ["ArchitectureContextService:Builds concise architecture context for a node. It includes summaries, hierarchy, health, guidance summary, and drill-down paths."],
            "ArchitectureReviews": ["ArchitectureReviewService:Captures review, finding, challenge, and revision governance around architecture nodes. It supports cautious completeness review without automated judgment."],
            "ArchitectureADRs": ["ArchitectureDecisionRecordService:Stores proposed, accepted, and superseded architecture decision records. It gives architecture retrieval the historical rationale behind the current design."],
            "ArchitectureGuidance": ["ArchitectureGuidanceService:Manages accepted principles and intent and derives guidance. It turns governance artifacts into future-work constraints."],
            "GuidanceContext": ["ArchitectureGuidanceContextService:Builds GUIDECTX packages from effective inherited guidance. It gives MCP consumers and workers a compact, traceable guidance artifact."],
            "WorkContext": ["ArchitectureWorkContextService:Builds WORKCTX packages from scope, guidance, and direct impact relationships. It is the first operational bridge from architecture knowledge to future worker context."],
            "CapabilityRegistry": ["CapabilityRegistryService:Registers capability definitions, categories, handlers, and access metadata. It ensures external discovery describes capabilities without granting authority."],
            "Discovery": ["MCPDiscoveryService:Builds filtered and paginated tool discovery responses. It keeps the expanding MCP catalog usable for external models."],
            "FacadeExecution": ["MCPFacadeService:Receives MCP tool calls and routes them through capability execution. It preserves Ageix governance at the external boundary."],
            "TransportBridge": ["MCPTransportBridge:Hosts the MCP transport endpoint and protocol bridge. It connects ChatGPT and future clients to Ageix capability discovery and execution."],
            "ExternalAgentAccess": ["ExternalAgentAccessService:Packages schemas, workflow hints, related tools, and external discoverability metadata. It lets model clients understand how to interact safely."],
            "OAuthJWTIdentity": ["JWTAuthService:Validates token issuer, audience, scopes, and JWKS signatures. It binds agent identity to trusted OAuth tokens instead of caller-provided headers."],
            "Authorization": ["AuthorizationService:Maps authenticated identity to allowed projects and capabilities. It denies requests where scope, client, or project authority is insufficient."],
            "TrustBoundaries": ["TrustBoundaryService:Enforces cross-boundary restrictions such as repo access denial, workflow bypass protection, and client/provider mismatch rejection. It assumes every integration point can be misused."],
            "ClientAdmission": ["ClientAdmissionService:Manages allowlists, placeholders, and denylisted clients. It keeps unsupported or untrusted model providers out of governed execution paths."],
            "CapabilitySecurity": ["CapabilitySecurityService:Evaluates per-capability access levels and repository access metadata. It separates discovery, read, governed write, and execution authority."],
            "Identity": ["IdentityContextService:Returns the current authenticated agent and project identity. It is intentionally derived from token context rather than agent headers."],
            "SessionState": ["SessionStateService:Maintains session continuity for external and internal interactions. It lets Ageix preserve context while treating models as stateless participants."],
            "WorkflowContext": ["WorkflowContextService:Retrieves current proposal, consultation, decision, and execution workflow state. It helps tools offer relevant next actions."],
            "Persistence": ["PersistenceService:Writes durable JSON artifacts and indexes for governance records. It favors inspectable state that can be validated and repaired cautiously."],
            "SharedConversation": [
                "ConversationService:Opens, transitions, and retrieves governed shared conversations and their rules of engagement. It is the entry point that binds participants, state, and turn history into one addressable conversation.",
                "TurnService:Appends and retrieves immutable, append-only conversation turns. It enforces the directed-question response contract and never exposes a mutation path for committed turns.",
                "ParticipantService:Tracks registered participants and per-role directed-question obligations for a conversation. It resolves confidence thresholds per agent role so escalation policy stays consistent.",
                "HandoffService:Serializes and retrieves governed HANDOFF_PACKAGE artifacts summarizing a conversation for transfer. It packages participants, rules of engagement, and recent turns so context survives a handoff between agents.",
            ],
            "ValidationAgent": ["ValidationAgentService:Executes validation profiles and normalizes test results. It reports success, failure, and evidence metadata without changing source code."],
            "ValidationProfiles": ["ValidationProfileService:Defines approved validation profiles and command scopes. It makes validation repeatable and governable."],
            "SmokeEvidence": ["SmokeEvidenceService:Creates temporary smoke-related evidence and cleanup rules. It supports immediate post-smoke inspection without long-term history pollution."],
            "ReadinessValidation": ["ReadinessValidationService:Checks internet exposure, TLS, reputation, auth, and MCP readiness. It documents operational assumptions before public use."],
            "APILayer": ["FastAPIApp:Hosts the Ageix HTTP application and dependency graph. It is the runtime container for web routes, health, and MCP integration."],
            "Routes": ["RouteModules:Map HTTP requests to authenticated service calls. Route code should stay thin and defer governance to services."],
            "RequestContext": ["RequestContextService:Builds request identity, project, client, and session metadata. It passes trusted context into capability execution."],
            "Storage": ["ArtifactStorageService:Persists architecture, evidence, proposals, and generated packages under .ageix. It provides simple inspectable storage for local-first operation."],
            "Configuration": ["ConfigurationService:Loads controls, auth, exposure, and runtime settings. It keeps behavior configurable instead of hard-coded."],
            "Runtime": ["RuntimeService:Represents the local VM, Python, Uvicorn, and process execution environment. It is the operational home of the local-first gateway."],
            "Deployment": ["DeploymentService:Captures nginx, TLS, DNS, Keycloak, and public endpoint topology. It documents how Ageix is exposed safely outside the local machine."],
        }
        for comp_key, service_rows in services.items():
            parent = component_nodes[comp_key]
            summaries = []
            for row in service_rows:
                service_name, desc = row.split(":", 1)
                svc_key = self._safe_key(service_name)
                svc = self._ensure_node(
                    key=svc_key,
                    architecture_id=f"ARCH-AGEIX-SVC-{svc_key.upper()}",
                    name=service_name,
                    node_key=svc_key,
                    path=f"{parent.path}.{svc_key}",
                    node_type="service",
                    parent_id=parent.architecture_id,
                    description=desc.strip(),
                    metadata={"lowest_architecture_level": True},
                )
                summaries.append({"architecture_id": svc.architecture_id, "name": svc.name, "summary": svc.description})
                nodes[svc_key] = svc
            parent.metadata["service_summaries"] = summaries
            parent.metadata["service_count"] = len(summaries)
            self.registry.upsert_node(parent)

        self._apply_relationships(nodes)
        return nodes

    def _apply_relationships(self, nodes: dict[str, ArchitectureNode]) -> None:
        relationships = {
            "MCPPlatform": {"depends_on": ["SecurityPlatform", "SessionPlatform", "CapabilityRegistry"], "provides_to": ["ExternalAgentAccess"]},
            "EvidencePlatform": {"depends_on": ["GovernancePlatform"], "provides_to": ["ArchitecturePlatform", "ValidationPlatform", "DecisionTrace"]},
            "ArchitecturePlatform": {"depends_on": ["EvidencePlatform", "GovernancePlatform"], "provides_to": ["WorkerPlatform", "MCPPlatform"]},
            "WorkerPlatform": {"depends_on": ["GovernancePlatform", "ArchitecturePlatform", "EvidencePlatform"], "governed_by": ["GovernancePolicy"]},
            "SecurityPlatform": {"provides_to": ["MCPPlatform", "WebPlatform", "CapabilitySecurity"]},
            "WorkContext": {"depends_on": ["GuidanceContext", "ArchitectureRelationships"], "provides_to": ["FutureWorkers", "Planner"]},
            "GuidanceContext": {"depends_on": ["ArchitectureGuidance", "ArchitectureADRs"], "provides_to": ["WorkContext", "MCPPlatform"]},
            "Discovery": {"depends_on": ["CapabilityRegistry"], "provides_to": ["ExternalAgentAccess"]},
            "OAuthJWTIdentity": {"provides_to": ["Authorization", "Identity", "RequestContext"]},
            "EvidenceBroker": {"depends_on": ["ProposalSystem", "GovernancePolicy"], "provides_to": ["EvidencePackages"]},
        }
        for source_key, rels in relationships.items():
            node = nodes.get(source_key)
            if not node:
                continue
            meta_rels: dict[str, list[dict[str, str]]] = {}
            for rel_type, target_keys in rels.items():
                meta_rels[rel_type] = []
                for target_key in target_keys:
                    target = nodes.get(target_key)
                    if target:
                        meta_rels[rel_type].append({"architecture_id": target.architecture_id, "path": target.path, "name": target.name})
            node.metadata["relationships"] = meta_rels
            node.metadata["relationship_seed"] = self.VERSION
            self.registry.upsert_node(node)

    def _populate_principles(self, nodes: dict[str, ArchitectureNode]) -> dict[str, str]:
        rows = [
            ("ARCHPRIN-AGEIX-GOVERNANCE-FIRST", "PRIN-0001", "Governance before execution", "Ageix must route meaningful work through governed proposals, approval controls, and traceable authority before execution occurs.", "Prevents autonomous or external actors from bypassing human authority.", ["Ageix", "GovernancePlatform", "WorkerPlatform"]),
            ("ARCHPRIN-AGEIX-EVIDENCE-FIRST", "PRIN-0002", "Evidence before decisions", "Architectural and implementation decisions should be supported by scoped evidence packages where available.", "Evidence gives decisions a stable factual basis and preserves explainability.", ["Ageix", "EvidencePlatform", "ArchitecturePlatform"]),
            ("ARCHPRIN-AGEIX-DETERMINISTIC-FIRST", "PRIN-0003", "Deterministic before intelligent", "Ageix should prefer deterministic, inspectable resolution before semantic inference or model judgment.", "This keeps governance testable and allows intelligence to be layered later.", ["Ageix", "ArchitecturePlatform", "WorkerPlatform"]),
            ("ARCHPRIN-AGEIX-IMMUTABLE-HISTORY", "PRIN-0004", "Immutable historical artifacts", "Accepted evidence packages, ADRs, guidance contexts, work contexts, and decision traces should preserve historical state.", "Historical explainability requires snapshots that do not silently change.", ["Ageix", "EvidencePlatform", "ArchitecturePlatform", "GovernancePlatform"]),
            ("ARCHPRIN-AGEIX-SECURE-BOUNDARIES", "PRIN-0005", "Secure external boundaries", "External MCP clients must authenticate, authorize, and remain constrained by capability governance and trust boundaries.", "Trusted clients can still misuse access, so boundaries must be enforced in layers.", ["Ageix", "MCPPlatform", "SecurityPlatform"]),
            ("ARCHPRIN-AGEIX-SUMMARY-FIRST", "PRIN-0006", "Summary-first retrieval", "MCP and worker-facing context should be concise by default with explicit drill-down paths for detail.", "This keeps external model context useful without oversized payloads.", ["Ageix", "MCPPlatform", "EvidencePlatform", "ArchitecturePlatform"]),
        ]
        result = {}
        for pid, number, title, statement, rationale, keys in rows:
            arch_ids = [nodes[key].architecture_id for key in keys if key in nodes]
            principle = ArchitecturePrinciple(
                principle_id=pid,
                principle_number=number,
                project_id=self.PROJECT_ID,
                title=title,
                statement=statement,
                rationale=rationale,
                status=ArchitectureGuidanceStatus.ACCEPTED,
                scope="project",
                proposal_id=f"PROP-BASELINE-{number}",
                decision_trace_id=f"TRACE-BASELINE-{number}",
                architecture_ids=arch_ids,
                created_by="architecture_baseline_service",
                approved_by="chair",
                approved_at=self._now(),
                metadata={"seeded_by": "sprint_18_10", "canonical_ageix_baseline": True},
            )
            self._write_once(self.principle_root / principle.principle_id / "principle.json", principle.model_dump(mode="json"))
            result[pid] = pid
        return result

    def _populate_intents(self, nodes: dict[str, ArchitectureNode], principle_ids: dict[str, str]) -> dict[str, str]:
        rows = [
            ("ARCHINTENT-AGEIX-LOCAL-FIRST", "INTENT-0001", "Local-first AI gateway", "Ageix should run primarily under local ownership while exposing carefully governed public integration points.", "The project should preserve local control, inspectable state, and practical self-hosting while allowing external model collaboration through MCP.", ["Ageix", "InfrastructurePlatform", "MCPPlatform"]),
            ("ARCHINTENT-AGEIX-GOVERNED-MULTI-AGENT", "INTENT-0002", "Governed multi-agent collaboration", "Ageix should allow multiple agents and advisors to contribute without granting unchecked authority.", "Chair, proposals, consultations, validation, and capability boundaries should keep collaboration safe and auditable.", ["Ageix", "GovernancePlatform", "WorkerPlatform"]),
            ("ARCHINTENT-AGEIX-EVIDENCE-DRIVEN", "INTENT-0003", "Evidence-driven decisions", "Ageix should ground decisions and reviews in reusable evidence packages and decision traces.", "This enables historical explanation and avoids repeating context collection.", ["Ageix", "EvidencePlatform", "GovernancePlatform"]),
            ("ARCHINTENT-AGEIX-COMPOSABLE-CAPABILITIES", "INTENT-0004", "Composable capability architecture", "Ageix capabilities should be discoverable, metadata-rich, governed, and independently extensible.", "This lets MCP, workers, and future UI layers compose safe operations without hardwiring every flow.", ["Ageix", "MCPPlatform", "WorkerPlatform"]),
            ("ARCHINTENT-AGEIX-SELF-DESCRIBING", "INTENT-0005", "Self-describing architecture", "Ageix should document its own domains, components, services, relationships, principles, intent, and ADRs as governed architecture artifacts.", "Future workers should understand where work belongs and what must be preserved before acting.", ["Ageix", "ArchitecturePlatform"]),
        ]
        result = {}
        for iid, number, title, summary, details, keys in rows:
            arch_ids = [nodes[key].architecture_id for key in keys if key in nodes]
            intent = ArchitectureIntent(
                intent_id=iid,
                intent_number=number,
                project_id=self.PROJECT_ID,
                title=title,
                summary=summary,
                details=details,
                status=ArchitectureGuidanceStatus.ACCEPTED,
                scope="project",
                future_considerations=["Expand service-to-file and test-to-service mappings after canonical architecture baseline is stable."],
                proposal_id=f"PROP-BASELINE-{number}",
                decision_trace_id=f"TRACE-BASELINE-{number}",
                architecture_ids=arch_ids,
                principle_ids=list(principle_ids.values()),
                created_by="architecture_baseline_service",
                approved_by="chair",
                approved_at=self._now(),
                metadata={"seeded_by": "sprint_18_10", "canonical_ageix_baseline": True},
            )
            self._write_once(self.intent_root / intent.intent_id / "intent.json", intent.model_dump(mode="json"))
            result[iid] = iid
        return result

    def _populate_adrs(self, nodes: dict[str, ArchitectureNode]) -> dict[str, str]:
        rows = [
            ("ADR-AGEIX-GOVERNANCE-FIRST", "ADR-0001", "Governance before execution", "Ageix adopted governed proposals and Chair authority before autonomous execution.", "All meaningful execution must preserve governance and approval boundaries.", ["Ageix", "GovernancePlatform"]),
            ("ADR-AGEIX-CONSULTATION", "ADR-0002", "Consultation framework", "Ageix introduced structured advisory consultations for proposals.", "Advisors may inform decisions but cannot directly mutate governed state.", ["ConsultationFramework", "GovernancePlatform"]),
            ("ADR-AGEIX-EVIDENCE-PACKAGES", "ADR-0003", "Evidence package architecture", "Ageix introduced immutable evidence packages as reusable decision context.", "Evidence packages preserve provenance, summaries, and traceability across decisions.", ["EvidencePackages", "EvidencePlatform"]),
            ("ADR-AGEIX-EVIDENCE-FRESHNESS", "ADR-0004", "Evidence freshness model", "Ageix added freshness evaluation for historical evidence.", "Evidence consumers should know when package context may be stale.", ["FreshnessEvaluation", "EvidencePlatform"]),
            ("ADR-AGEIX-MCP-REGISTRY", "ADR-0005", "MCP capability registry", "Ageix exposed capabilities through a governed registry rather than direct service access.", "Discovery metadata must not grant authority to execute.", ["CapabilityRegistry", "MCPPlatform"]),
            ("ADR-AGEIX-MCP-DISCOVERY", "ADR-0006", "MCP discovery ergonomics", "Ageix made capability discovery metadata-rich, filterable, and summary-first.", "External model clients need usable discovery as the capability catalog grows.", ["Discovery", "MCPPlatform"]),
            ("ADR-AGEIX-TRUST-BOUNDARY", "ADR-0007", "MCP trust boundary", "Ageix hardened external model access against provider mismatch, unknown clients, denied clients, and workflow bypass.", "Trusted models can still abuse access, so governance must defend against misuse.", ["TrustBoundaries", "SecurityPlatform"]),
            ("ADR-AGEIX-OAUTH-JWT", "ADR-0008", "OAuth/JWT identity model", "Ageix adopted official OAuth/JWT identity validation with JWKS discovery.", "Agent identity must come from trusted tokens, not caller-supplied headers.", ["OAuthJWTIdentity", "SecurityPlatform"]),
            ("ADR-AGEIX-ARCH-REGISTRY", "ADR-0009", "Architecture registry", "Ageix introduced a first-class architecture registry and hierarchy.", "Architecture context should be retrieved without reading the full repository.", ["ArchitectureRegistry", "ArchitectureHierarchy"]),
            ("ADR-AGEIX-ARCH-GUIDANCE", "ADR-0010", "Architecture guidance model", "Ageix introduced principles, intent, and derived guidance.", "Future work should preserve architectural rules and direction.", ["ArchitectureGuidance", "ArchitecturePlatform"]),
            ("ADR-AGEIX-GUIDECTX", "ADR-0011", "Guidance context packages", "Ageix introduced GUIDECTX packages for summary-first effective guidance retrieval.", "External consumers need scoped guidance with lineage and traceability.", ["GuidanceContext", "ArchitecturePlatform"]),
            ("ADR-AGEIX-WORKCTX", "ADR-0012", "Work context packages", "Ageix introduced WORKCTX packages for architecture-aware work analysis.", "Workers should know affected scope, guidance, and direct impacts before execution.", ["WorkContext", "WorkerPlatform"]),
            ("ADR-AGEIX-SELF-ARCH", "ADR-0013", "Canonical Ageix architecture baseline", "Ageix began documenting itself as the first real consumer of the architecture platform.", "Self-description validates the platform and provides design truth for future work.", ["Ageix", "ArchitecturePlatform"]),
        ]
        result = {}
        for aid, number, title, context, decision, keys in rows:
            arch_ids = [nodes[key].architecture_id for key in keys if key in nodes]
            adr = ArchitectureDecisionRecord(
                adr_id=aid,
                adr_number=number,
                project_id=self.PROJECT_ID,
                title=title,
                status=ArchitectureDecisionRecordStatus.ACCEPTED,
                context=context,
                decision=decision,
                rationale="Seeded from known Ageix sprint history to establish the canonical project architecture baseline.",
                consequences=["Provides historical rationale for architecture retrieval and future work context."],
                future_considerations=["Expand with additional ADRs as full repository documentation matures."],
                proposal_id=f"PROP-BASELINE-{number}",
                decision_trace_id=f"TRACE-BASELINE-{number}",
                architecture_ids=arch_ids,
                created_by="architecture_baseline_service",
                approved_by="chair",
                approved_at=self._now(),
                metadata={"seeded_by": "sprint_18_10", "canonical_ageix_baseline": True},
            )
            self._write_once(self.adr_root / adr.adr_id / "adr.json", adr.model_dump(mode="json"))
            result[aid] = aid
        return result

    def _link_guidance_to_adrs(self, principle_ids: dict[str, str], intent_ids: dict[str, str], adr_ids: dict[str, str]) -> None:
        # Keep linkage intentionally broad for the seed baseline: these artifacts describe the whole project.
        for path in self.principle_root.glob("ARCHPRIN-AGEIX-*/principle.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["adr_ids"] = sorted(adr_ids.values())
            path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        for path in self.intent_root.glob("ARCHINTENT-AGEIX-*/intent.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["adr_ids"] = sorted(adr_ids.values())
            data["principle_ids"] = sorted(principle_ids.values())
            path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _ensure_baseline_review(self, project: ArchitectureNode) -> dict[str, Any]:
        existing = self.registry.list_reviews(project_id=self.PROJECT_ID, architecture_id=project.architecture_id, limit=50).get("reviews", [])
        for review in existing:
            if review.get("metadata", {}).get("baseline_version") == self.VERSION:
                return review
        review = self.registry.submit_review(
            architecture_id_or_path=project.architecture_id,
            reviewer_id="lex",
            project_id=self.PROJECT_ID,
            summary="Sprint 18.10 cautious completeness review for the canonical Ageix architecture baseline.",
            rationale="Review verifies that the baseline is populated enough for retrieval, guidance context, and work context. It does not score architecture quality or recommend repairs.",
            no_findings=True,
            metadata={"baseline_version": self.VERSION, "review_scope": "coverage_and_consistency_only", "no_quality_scoring": True},
            provider="chatGPT",
        )
        return review.model_dump(mode="json")

    def _ensure_node(self, *, key: str, architecture_id: str, name: str, node_key: str, path: str, node_type: str, description: str, parent_id: str | None = None, metadata: dict[str, Any] | None = None) -> ArchitectureNode:
        existing = self.registry.get_node(architecture_id) or self.registry.get_node(path)
        meta = {"official": True, "seeded_by": "sprint_18_10", "canonical_ageix_baseline": True, **dict(metadata or {})}
        if existing:
            existing.name = name
            existing.node_key = node_key
            existing.path = path
            existing.parent_id = parent_id
            existing.node_type = ArchitectureNodeType(node_type)
            existing.description = description
            existing.description_state = ArchitectureDescriptionState.APPROVED
            existing.approved_by = existing.approved_by or "chair"
            existing.approved_at = existing.approved_at or self._now()
            existing.metadata = {**dict(existing.metadata or {}), **meta}
            return self.registry.upsert_node(existing)
        node = self.registry.create_node(
            project_id=self.PROJECT_ID,
            architecture_id=architecture_id,
            name=name,
            node_key=node_key,
            path=path,
            node_type=node_type,
            parent_id=parent_id,
            description=description,
            metadata=meta,
        )
        node.description_state = ArchitectureDescriptionState.APPROVED
        node.approved_by = "chair"
        node.approved_at = self._now()
        return self.registry.upsert_node(node)

    def _write_once(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _load_seed_files(self, root: Path) -> list[dict[str, Any]]:
        if not root.exists():
            return []
        rows = []
        for path in root.glob("ARCH*/*json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("project_id") == self.PROJECT_ID and data.get("metadata", {}).get("canonical_ageix_baseline"):
                rows.append(data)
        if root.name == "adrs":
            rows = []
            for path in root.glob("ADR-AGEIX-*/adr.json"):
                rows.append(json.loads(path.read_text(encoding="utf-8")))
        return rows

    def _safe_key(self, value: str) -> str:
        return "".join(ch for ch in str(value) if ch.isalnum()) or "Service"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
