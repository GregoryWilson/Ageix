from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DeploymentMode(str, Enum):
    LOCAL = "local"
    LAN = "lan"
    INTERNET = "internet"


class ExposurePolicy(str, Enum):
    LOCAL_ONLY = "local_only"
    LAN_ONLY = "lan_only"
    INTERNET_READY = "internet_ready"


class ReverseProxyProvider(str, Enum):
    NONE = "none"
    NGINX = "nginx"
    TRAEFIK = "traefik"


class CertificateSource(str, Enum):
    NONE = "none"
    SELF_SIGNED = "self_signed"
    LOCAL_CA = "local_ca"
    LETS_ENCRYPT = "lets_encrypt"
    CUSTOM = "custom"


class EndpointClassification(str, Enum):
    PUBLIC_METADATA = "public_metadata"
    AUTHENTICATED_METADATA = "authenticated_metadata"
    GOVERNANCE_PROTECTED = "governance_protected"
    INTERNAL_ONLY = "internal_only"


class TrustBoundaryLevel(str, Enum):
    UNAUTHENTICATED_TRAFFIC = "unauthenticated_traffic"
    AUTHENTICATED_CLIENT = "authenticated_client"
    ADMITTED_CLIENT = "admitted_client"
    IDENTITY_VALIDATED = "identity_validated"
    CAPABILITY_AUTHORIZED = "capability_authorized"
    GOVERNED_ACTOR = "governed_actor"


class AccessDecisionPolicy(str, Enum):
    DENY = "deny"
    APPROVED = "approved"
    EXPLICIT_APPROVAL = "explicit_approval"


class TrafficMonitorMode(str, Enum):
    DISABLED = "disabled"
    OBSERVE_ONLY = "observe_only"
    RECOMMEND_BLOCK = "recommend_block"
    AUTO_BLOCK = "auto_block"


class TrafficSignalType(str, Enum):
    FAILED_AUTH = "failed_auth"
    REPEATED_401 = "repeated_401"
    REPEATED_403 = "repeated_403"
    REPEATED_404 = "repeated_404"
    REPEATED_429 = "repeated_429"
    REPEATED_500 = "repeated_500"
    MALFORMED_REQUEST = "malformed_request"
    SUSPICIOUS_USER_AGENT = "suspicious_user_agent"
    REPEATED_CLIENT_DENIAL = "repeated_client_denial"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class TrafficActionPolicy(str, Enum):
    NONE = "none"
    AUDIT_ONLY = "audit_only"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    TEMPORARY_BLOCK = "temporary_block"
    PERMANENT_BLOCK = "permanent_block"


class EmergencyMode(str, Enum):
    NORMAL = "normal"
    RESTRICTED = "restricted"
    LOCKDOWN = "lockdown"


class ExposureMaturityLevel(str, Enum):
    LEVEL_0_LOCAL = "level_0_local"
    LEVEL_1_LAN = "level_1_lan"
    LEVEL_2_INTERNET_READY = "level_2_internet_ready"
    LEVEL_3_PUBLIC = "level_3_public"
    LEVEL_4_REPUTATION_HARDENED = "level_4_reputation_hardened"
    LEVEL_5_EXTERNAL_AGENT_READY = "level_5_external_agent_ready"


class SecurityHeaderConfiguration(BaseModel):
    hsts_enabled: bool = False
    x_content_type_options: str = "nosniff"
    x_frame_options: str = "DENY"
    referrer_policy: str = "no-referrer"
    content_security_policy: str = "default-src 'none'; frame-ancestors 'none'"


class CertificateRotationConfiguration(BaseModel):
    renewal_days_before_expiration: int = Field(default=30, ge=1)
    expiration_warning_days: int = Field(default=14, ge=1)
    auto_renew_enabled: bool = False


class RequestCorrelationContext(BaseModel):
    proxy_request_id: str | None = None
    api_request_id: str
    governance_request_id: str | None = None
    audit_correlation_id: str | None = None

    @property
    def correlation_chain(self) -> list[str]:
        return [item for item in [self.proxy_request_id, self.api_request_id, self.governance_request_id, self.audit_correlation_id] if item]

    @property
    def preserved(self) -> bool:
        return bool(self.api_request_id and self.audit_correlation_id)


class ForwardedHeaderContext(BaseModel):
    x_forwarded_for: str | None = None
    x_forwarded_proto: str | None = None
    x_forwarded_host: str | None = None
    x_request_id: str | None = None

    @property
    def preserves_client_identity(self) -> bool:
        return bool(self.x_forwarded_for and self.x_forwarded_proto and self.x_forwarded_host)


class GovernanceContextSnapshot(BaseModel):
    client_id: str
    session_id: str
    project_id: str
    workflow_id: str | None = None
    proposal_id: str | None = None
    correlation_id: str | None = None

    @property
    def preserved_through_proxy(self) -> bool:
        return bool(self.client_id and self.session_id and self.project_id)


class MCPTransportValidation(BaseModel):
    discovery_ok: bool
    invocation_path_ok: bool
    metadata_projection_ok: bool
    governance_protected: bool
    tls_boundary_ok: bool

    @property
    def ready(self) -> bool:
        return all([self.discovery_ok, self.invocation_path_ok, self.metadata_projection_ok, self.governance_protected, self.tls_boundary_ok])


class ReverseProxyTemplate(BaseModel):
    provider: ReverseProxyProvider
    hostname: str
    upstream_host: str
    upstream_port: int
    tls_certificate_path: str
    tls_private_key_path: str
    content: str


class ExposureMaturityAssessment(BaseModel):
    current_level: ExposureMaturityLevel
    target_level: ExposureMaturityLevel
    next_requirements: list[str] = Field(default_factory=list)



class DeploymentTopology(BaseModel):
    deployment_mode: DeploymentMode = DeploymentMode.LOCAL
    hostname: str = "localhost"
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8443, ge=1, le=65535)
    reverse_proxy_required: bool = False
    tls_required: bool = False
    public_dns_required: bool = False


class ReverseProxyConfiguration(BaseModel):
    provider: ReverseProxyProvider = ReverseProxyProvider.NONE
    enabled: bool = False
    tls_termination: bool = False
    forwards_host: bool = True
    forwards_proto: bool = True
    forwards_client_ip: bool = True
    upstream_host: str = "127.0.0.1"
    upstream_port: int = Field(default=8443, ge=1, le=65535)

    @property
    def ready(self) -> bool:
        if self.provider == ReverseProxyProvider.NONE:
            return not self.enabled
        return self.enabled and bool(self.upstream_host) and bool(self.upstream_port)


class TLSConfiguration(BaseModel):
    enabled: bool = False
    required: bool = False
    hostname: str = "localhost"
    certificate_source: CertificateSource = CertificateSource.NONE
    certificate_configured: bool = False
    hostname_matches_certificate: bool = False
    certificate_secret_ref: str | None = None
    private_key_secret_ref: str | None = None

    @property
    def ready(self) -> bool:
        if not self.required:
            return True
        return self.enabled and self.certificate_source != CertificateSource.NONE and self.certificate_configured and self.hostname_matches_certificate


class DNSReadinessConfiguration(BaseModel):
    hostname: str = "wilsongpt.com"
    dns_provider: str | None = None
    expected_public_ip: str | None = None
    dns_configured: bool = False
    dns_matches_expected_target: bool = False

    @property
    def ready(self) -> bool:
        return self.dns_configured and self.dns_matches_expected_target


class NetworkSecurityConfiguration(BaseModel):
    allowed_ips: list[str] = Field(default_factory=list)
    blocked_ips: list[str] = Field(default_factory=list)
    allowed_countries: list[str] = Field(default_factory=list)
    blocked_countries: list[str] = Field(default_factory=list)
    allowed_asns: list[str] = Field(default_factory=list)
    blocked_asns: list[str] = Field(default_factory=list)
    reputation_filter_enabled: bool = False
    rate_limit_enabled: bool = False


class RateLimitConfiguration(BaseModel):
    enabled: bool = False
    requests_per_minute: int = Field(default=60, ge=1)
    burst_limit: int = Field(default=20, ge=1)
    scope: str = "ip"


class SecretReferenceConfiguration(BaseModel):
    certificate_secret_ref: str | None = None
    private_key_secret_ref: str | None = None
    api_token_secret_ref: str | None = None
    admin_credential_secret_ref: str | None = None


class GovernanceTimerDefaults(BaseModel):
    explicit_approval_ttl_seconds: int = Field(default=3600, ge=1)
    temporary_block_ttl_seconds: int = Field(default=900, ge=1)
    session_trust_ttl_seconds: int = Field(default=86400, ge=1)
    client_admission_ttl_seconds: int = Field(default=86400, ge=1)
    readiness_assessment_ttl_seconds: int = Field(default=300, ge=1)
    audit_retention_days: int = Field(default=365, ge=1)


class OutboundNetworkPolicy(BaseModel):
    policy: AccessDecisionPolicy = AccessDecisionPolicy.DENY
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    allowed_methods: list[str] = Field(default_factory=list)
    requires_governance: bool = True
    audit_required: bool = True

    def evaluate(self, *, domain: str, method: str = "GET", approval_id: str | None = None) -> dict[str, Any]:
        normalized_method = method.upper()
        if self.policy == AccessDecisionPolicy.DENY:
            return {"allowed": False, "reason": "outbound_policy_denied"}
        if domain in self.blocked_domains:
            return {"allowed": False, "reason": "outbound_domain_blocked"}
        if self.allowed_domains and domain not in self.allowed_domains:
            return {"allowed": False, "reason": "outbound_domain_not_allowed"}
        if self.allowed_methods and normalized_method not in [item.upper() for item in self.allowed_methods]:
            return {"allowed": False, "reason": "outbound_method_not_allowed"}
        if self.policy == AccessDecisionPolicy.EXPLICIT_APPROVAL and not approval_id:
            return {"allowed": False, "reason": "explicit_outbound_approval_required"}
        return {"allowed": True, "reason": "outbound_policy_approved"}


class InboundActionPolicy(BaseModel):
    policy: AccessDecisionPolicy = AccessDecisionPolicy.DENY
    capability_id: str | None = None
    audit_required: bool = True


class TrafficMonitorConfiguration(BaseModel):
    enabled: bool = False
    mode: TrafficMonitorMode = TrafficMonitorMode.OBSERVE_ONLY
    signals: list[TrafficSignalType] = Field(default_factory=lambda: [
        TrafficSignalType.FAILED_AUTH,
        TrafficSignalType.REPEATED_401,
        TrafficSignalType.REPEATED_403,
        TrafficSignalType.REPEATED_500,
    ])
    action_policy: TrafficActionPolicy = TrafficActionPolicy.AUDIT_ONLY
    audit_required: bool = True

    @property
    def can_authorize_access(self) -> bool:
        return False


class TemporaryBlockRecord(BaseModel):
    source_ip: str | None = None
    client_id: str | None = None
    block_reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    @classmethod
    def with_default_ttl(cls, *, block_reason: str, timers: GovernanceTimerDefaults, source_ip: str | None = None, client_id: str | None = None) -> "TemporaryBlockRecord":
        created = datetime.now(timezone.utc)
        return cls(
            source_ip=source_ip,
            client_id=client_id,
            block_reason=block_reason,
            created_at=created,
            expires_at=created + timedelta(seconds=timers.temporary_block_ttl_seconds),
        )

    def is_active(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return True
        return (now or datetime.now(timezone.utc)) < self.expires_at


class ExplicitApprovalArtifact(BaseModel):
    approval_id: str = Field(min_length=1)
    requested_by_client: str = Field(min_length=1)
    requested_action: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    audit_id: str | None = None

    @classmethod
    def with_default_ttl(cls, *, approval_id: str, requested_by_client: str, requested_action: str, timers: GovernanceTimerDefaults, **kwargs: Any) -> "ExplicitApprovalArtifact":
        created = datetime.now(timezone.utc)
        return cls(
            approval_id=approval_id,
            requested_by_client=requested_by_client,
            requested_action=requested_action,
            created_at=created,
            expires_at=created + timedelta(seconds=timers.explicit_approval_ttl_seconds),
            **kwargs,
        )

    def is_valid(self, now: datetime | None = None) -> bool:
        if not self.approved_by:
            return False
        if self.expires_at is None:
            return True
        return (now or datetime.now(timezone.utc)) < self.expires_at


class EndpointInventoryItem(BaseModel):
    path: str = Field(min_length=1)
    classification: EndpointClassification
    owner: str = "ageix"
    auth_required: bool = True
    governance_required: bool = False
    internet_allowed: bool = False
    methods: list[str] = Field(default_factory=lambda: ["GET"])




class ReputationProviderHook(BaseModel):
    provider_name: str = Field(min_length=1)
    enabled: bool = False
    api_secret_ref: str | None = None
    observe_only: bool = True


class NetworkReputationControlConfiguration(BaseModel):
    ip_allowlists: list[str] = Field(default_factory=list)
    ip_blocklists: list[str] = Field(default_factory=list)
    country_controls: list[str] = Field(default_factory=list)
    asn_controls: list[str] = Field(default_factory=list)
    reputation_provider_hooks: list[ReputationProviderHook] = Field(default_factory=list)
    enforcement_enabled: bool = False
    audit_required: bool = True

    @property
    def configured(self) -> bool:
        return any([
            self.ip_allowlists,
            self.ip_blocklists,
            self.country_controls,
            self.asn_controls,
            self.reputation_provider_hooks,
        ])


class LetsEncryptReadinessConfiguration(BaseModel):
    hostname: str = "wilsongpt.com"
    acme_account_configured: bool = False
    http_01_ready: bool = False
    dns_01_ready: bool = False
    renewal_strategy_configured: bool = False
    certificate_issuance_requested: bool = False


class FirewallReadinessConfiguration(BaseModel):
    inbound_ports_required: list[int] = Field(default_factory=lambda: [80, 443])
    exposed_ports: list[int] = Field(default_factory=lambda: [443])
    tls_required: bool = True
    reverse_proxy_required: bool = True
    firewall_changes_applied: bool = False


class ScannerReadinessConfiguration(BaseModel):
    open_proxy_behavior: bool = False
    anonymous_execution: bool = False
    public_file_upload: bool = False
    unrestricted_outbound_relay: bool = False
    dangerous_default_endpoints: bool = False
    information_leakage: bool = False

    @property
    def safe_for_scanners(self) -> bool:
        return not any([
            self.open_proxy_behavior,
            self.anonymous_execution,
            self.public_file_upload,
            self.unrestricted_outbound_relay,
            self.dangerous_default_endpoints,
            self.information_leakage,
        ])


class ReputationReadinessAssessment(BaseModel):
    tls_reputation_ready: bool
    endpoint_reputation_ready: bool
    authentication_reputation_ready: bool
    abuse_response_ready: bool
    traffic_monitor_ready: bool
    rate_limit_ready: bool
    network_reputation_ready: bool
    scanner_ready: bool
    dns_ready: bool
    lets_encrypt_ready: bool
    firewall_ready: bool
    reputation_ready: bool
    blockers: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class InternetReadinessGate(BaseModel):
    technical_foundation_ready: bool
    lan_exposure_ready: bool
    internet_exposure_ready: bool
    reputation_ready: bool
    dns_ready: bool
    tls_reputation_ready: bool
    abuse_response_ready: bool
    blockers: list[str] = Field(default_factory=list)


class RegressionProfileName(str, Enum):
    SMOKE = "smoke"
    FOCUSED = "focused"
    REGRESSION_CORE = "regression_core"
    REGRESSION_FULL = "regression_full"


class RegressionProfile(BaseModel):
    name: RegressionProfileName
    description: str
    test_targets: list[str] = Field(default_factory=list)
    protects: list[str] = Field(default_factory=list)
    sprint_scoped: bool = False

class PublicReadinessAssessment(BaseModel):
    tls_ready: bool
    proxy_ready: bool
    topology_ready: bool
    exposure_policy_ready: bool
    admission_ready: bool
    identity_ready: bool
    authorization_ready: bool
    governance_ready: bool
    audit_ready: bool
    endpoint_inventory_ready: bool
    network_security_ready: bool
    dns_ready: bool = False
    technical_foundation_ready: bool = False
    lan_exposure_ready: bool = False
    reputation_ready: bool = False
    explicit_public_exposure_intent: bool = False
    internet_exposure_ready: bool = False
    blockers: list[str] = Field(default_factory=list)


class ExposureConfiguration(BaseModel):
    topology: DeploymentTopology = Field(default_factory=DeploymentTopology)
    exposure_policy: ExposurePolicy = ExposurePolicy.LOCAL_ONLY
    reverse_proxy: ReverseProxyConfiguration = Field(default_factory=ReverseProxyConfiguration)
    tls: TLSConfiguration = Field(default_factory=TLSConfiguration)
    dns: DNSReadinessConfiguration = Field(default_factory=DNSReadinessConfiguration)
    network_security: NetworkSecurityConfiguration = Field(default_factory=NetworkSecurityConfiguration)
    rate_limit: RateLimitConfiguration = Field(default_factory=RateLimitConfiguration)
    secrets: SecretReferenceConfiguration = Field(default_factory=SecretReferenceConfiguration)
    traffic_monitor: TrafficMonitorConfiguration = Field(default_factory=TrafficMonitorConfiguration)
    network_reputation_controls: NetworkReputationControlConfiguration = Field(default_factory=NetworkReputationControlConfiguration)
    lets_encrypt: LetsEncryptReadinessConfiguration = Field(default_factory=LetsEncryptReadinessConfiguration)
    firewall: FirewallReadinessConfiguration = Field(default_factory=FirewallReadinessConfiguration)
    scanner: ScannerReadinessConfiguration = Field(default_factory=ScannerReadinessConfiguration)
    timers: GovernanceTimerDefaults = Field(default_factory=GovernanceTimerDefaults)
    security_headers: SecurityHeaderConfiguration = Field(default_factory=SecurityHeaderConfiguration)
    certificate_rotation: CertificateRotationConfiguration = Field(default_factory=CertificateRotationConfiguration)
    emergency_mode: EmergencyMode = EmergencyMode.NORMAL
    explicit_public_exposure_intent: bool = False
    outbound_default_policy: AccessDecisionPolicy = AccessDecisionPolicy.DENY

    @model_validator(mode="after")
    def fail_closed_in_lockdown(self) -> "ExposureConfiguration":
        if self.emergency_mode == EmergencyMode.LOCKDOWN:
            self.exposure_policy = ExposurePolicy.LOCAL_ONLY
            self.explicit_public_exposure_intent = False
            self.outbound_default_policy = AccessDecisionPolicy.DENY
        return self
