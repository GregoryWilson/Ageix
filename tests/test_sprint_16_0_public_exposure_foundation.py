from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ageix_mcp.clients.client_registry import MCPClientDefinition, MCPClientRegistry
from models.public_exposure import (
    AccessDecisionPolicy,
    CertificateSource,
    DeploymentMode,
    EmergencyMode,
    EndpointClassification,
    ExplicitApprovalArtifact,
    ExposureConfiguration,
    ExposurePolicy,
    GovernanceTimerDefaults,
    OutboundNetworkPolicy,
    ReverseProxyConfiguration,
    ReverseProxyProvider,
    TemporaryBlockRecord,
    TLSConfiguration,
    TrafficMonitorConfiguration,
)
from services.deployment_topology_service import DeploymentTopologyService
from services.endpoint_inventory_service import EndpointInventoryService
from services.exposure_policy_service import ExposurePolicyService
from services.public_readiness_service import PublicReadinessService


def test_deployment_topology():
    service = DeploymentTopologyService()
    local = service.default_topology()
    assert local.deployment_mode == DeploymentMode.LOCAL
    assert local.hostname == "localhost"
    assert local.reverse_proxy_required is False
    assert local.public_dns_required is False

    internet = service.for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com")
    assert internet.hostname == "wilsongpt.com"
    assert internet.reverse_proxy_required is True
    assert internet.tls_required is True
    assert internet.public_dns_required is True


def test_exposure_policy():
    policy = ExposurePolicyService()
    config = ExposureConfiguration()
    assert policy.evaluate(config).allowed is True

    config.topology = DeploymentTopologyService().for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com")
    denied = policy.evaluate(config)
    assert denied.allowed is False
    assert "internet_deployment_requires_internet_ready_policy" in denied.blockers

    config.exposure_policy = ExposurePolicy.INTERNET_READY
    still_denied = policy.evaluate(config)
    assert still_denied.allowed is False
    assert "explicit_public_exposure_intent_required" in still_denied.blockers


def test_tls_configuration_model():
    optional = TLSConfiguration(required=False)
    assert optional.ready is True

    required = TLSConfiguration(required=True, enabled=False, hostname="wilsongpt.com", certificate_source=CertificateSource.LETS_ENCRYPT)
    assert required.ready is False

    ready = TLSConfiguration(
        required=True,
        enabled=True,
        hostname="wilsongpt.com",
        certificate_source=CertificateSource.LETS_ENCRYPT,
        certificate_configured=True,
        hostname_matches_certificate=True,
    )
    assert ready.ready is True


def test_reverse_proxy_configuration():
    disabled = ReverseProxyConfiguration()
    assert disabled.provider == ReverseProxyProvider.NONE
    assert disabled.ready is True

    nginx = ReverseProxyConfiguration(provider=ReverseProxyProvider.NGINX, enabled=True, tls_termination=True)
    assert nginx.ready is True
    assert nginx.forwards_client_ip is True


def test_endpoint_inventory():
    inventory = EndpointInventoryService().default_inventory()
    paths = {item.path: item for item in inventory}
    assert "/mcp" in paths
    assert paths["/mcp"].classification == EndpointClassification.GOVERNANCE_PROTECTED
    assert paths["/mcp"].governance_required is True
    assert all(item.internet_allowed is False for item in inventory)


def test_exposure_governance():
    service = ExposurePolicyService()
    config = ExposureConfiguration(
        topology=DeploymentTopologyService().for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com"),
        exposure_policy=ExposurePolicy.INTERNET_READY,
        explicit_public_exposure_intent=True,
    )
    assert service.evaluate(config).allowed is True
    assert service.governance_authoritative(config) is True


def test_public_readiness_assessment():
    assessment = PublicReadinessService().assess(ExposureConfiguration())
    assert assessment.tls_ready is True
    assert assessment.proxy_ready is True
    assert assessment.admission_ready is True
    assert assessment.identity_ready is True
    assert assessment.governance_ready is True
    assert assessment.audit_ready is True
    assert assessment.internet_exposure_ready is False

    internet_config = ExposureConfiguration(
        topology=DeploymentTopologyService().for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com"),
        exposure_policy=ExposurePolicy.INTERNET_READY,
        explicit_public_exposure_intent=True,
    )
    internet_config.reverse_proxy = ReverseProxyConfiguration(provider=ReverseProxyProvider.NGINX, enabled=True, tls_termination=True)
    internet_config.tls = TLSConfiguration(
        enabled=True,
        required=True,
        hostname="wilsongpt.com",
        certificate_source=CertificateSource.LETS_ENCRYPT,
        certificate_configured=True,
        hostname_matches_certificate=True,
    )
    internet_config.dns.dns_configured = True
    internet_config.dns.dns_matches_expected_target = True
    ready = PublicReadinessService().assess(internet_config)
    assert ready.internet_exposure_ready is True


def test_traffic_monitor_configuration():
    monitor = TrafficMonitorConfiguration()
    assert monitor.enabled is False
    assert monitor.can_authorize_access is False
    assert "repeated_401" in [signal.value for signal in monitor.signals]


def test_outbound_policy_defaults_to_deny():
    policy = OutboundNetworkPolicy()
    result = policy.evaluate(domain="api.github.com", method="GET")
    assert result["allowed"] is False
    assert result["reason"] == "outbound_policy_denied"


def test_outbound_policy_explicit_approval_requires_request():
    policy = OutboundNetworkPolicy(
        policy=AccessDecisionPolicy.EXPLICIT_APPROVAL,
        allowed_domains=["api.github.com"],
        allowed_methods=["GET"],
    )
    assert policy.evaluate(domain="api.github.com", method="GET")["reason"] == "explicit_outbound_approval_required"
    assert policy.evaluate(domain="api.github.com", method="GET", approval_id="APPROVAL-1")["allowed"] is True


def test_outbound_policy_approved_still_respects_scope():
    policy = OutboundNetworkPolicy(policy=AccessDecisionPolicy.APPROVED, allowed_domains=["api.github.com"], allowed_methods=["GET"])
    assert policy.evaluate(domain="api.github.com", method="GET")["allowed"] is True
    assert policy.evaluate(domain="evil.example", method="GET")["reason"] == "outbound_domain_not_allowed"
    assert policy.evaluate(domain="api.github.com", method="POST")["reason"] == "outbound_method_not_allowed"


def test_mcp_client_profile_carries_per_client_outbound_policy():
    registry = MCPClientRegistry(clients=[
        MCPClientDefinition(
            client_id="lex-test",
            display_name="Lex Test",
            provider="openai",
            enabled=True,
            outbound_network=OutboundNetworkPolicy(policy=AccessDecisionPolicy.EXPLICIT_APPROVAL, allowed_domains=["api.github.com"]),
        )
    ])
    profile = registry.require("lex-test").to_dict()
    assert profile["outbound_network"]["policy"] == "explicit_approval"
    assert profile["outbound_network"]["allowed_domains"] == ["api.github.com"]


def test_governance_timer_defaults():
    timers = GovernanceTimerDefaults()
    assert timers.explicit_approval_ttl_seconds == 3600
    assert timers.temporary_block_ttl_seconds == 900
    assert timers.readiness_assessment_ttl_seconds == 300


def test_explicit_approval_uses_default_ttl():
    timers = GovernanceTimerDefaults(explicit_approval_ttl_seconds=120)
    approval = ExplicitApprovalArtifact.with_default_ttl(
        approval_id="APPROVAL-1",
        requested_by_client="chatgpt",
        requested_action="outbound.get",
        timers=timers,
        approved_by="greg",
    )
    assert approval.expires_at is not None
    assert int((approval.expires_at - approval.created_at).total_seconds()) == 120
    assert approval.is_valid() is True


def test_temporary_block_uses_default_ttl():
    timers = GovernanceTimerDefaults(temporary_block_ttl_seconds=45)
    block = TemporaryBlockRecord.with_default_ttl(block_reason="repeated_401", timers=timers, source_ip="203.0.113.10")
    assert block.expires_at is not None
    assert int((block.expires_at - block.created_at).total_seconds()) == 45
    assert block.is_active() is True


def test_expired_approval_is_not_valid():
    approval = ExplicitApprovalArtifact(
        approval_id="APPROVAL-OLD",
        requested_by_client="chatgpt",
        requested_action="outbound.get",
        approved_by="greg",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert approval.is_valid() is False


def test_expired_block_is_not_active():
    block = TemporaryBlockRecord(
        source_ip="203.0.113.10",
        block_reason="repeated_401",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert block.is_active() is False


def test_emergency_lockdown_fails_closed():
    config = ExposureConfiguration(
        exposure_policy=ExposurePolicy.INTERNET_READY,
        explicit_public_exposure_intent=True,
        outbound_default_policy=AccessDecisionPolicy.APPROVED,
        emergency_mode=EmergencyMode.LOCKDOWN,
    )
    assert config.exposure_policy == ExposurePolicy.LOCAL_ONLY
    assert config.explicit_public_exposure_intent is False
    assert config.outbound_default_policy == AccessDecisionPolicy.DENY
