from __future__ import annotations

from models.public_exposure import (
    CertificateSource,
    DeploymentMode,
    DNSReadinessConfiguration,
    ExposureConfiguration,
    ExposurePolicy,
    FirewallReadinessConfiguration,
    LetsEncryptReadinessConfiguration,
    NetworkReputationControlConfiguration,
    NetworkSecurityConfiguration,
    RateLimitConfiguration,
    RegressionProfileName,
    ReputationProviderHook,
    ReverseProxyConfiguration,
    ReverseProxyProvider,
    ScannerReadinessConfiguration,
    TLSConfiguration,
    TrafficMonitorConfiguration,
    TrafficMonitorMode,
    TrafficSignalType,
)
from services.deployment_topology_service import DeploymentTopologyService
from services.regression_profile_service import RegressionProfileService
from services.reputation_readiness_service import ReputationReadinessService


def internet_readiness_config() -> ExposureConfiguration:
    return ExposureConfiguration(
        topology=DeploymentTopologyService().for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com"),
        exposure_policy=ExposurePolicy.INTERNET_READY,
        explicit_public_exposure_intent=False,
        reverse_proxy=ReverseProxyConfiguration(
            provider=ReverseProxyProvider.NGINX,
            enabled=True,
            tls_termination=True,
            upstream_host="127.0.0.1",
            upstream_port=8443,
        ),
        tls=TLSConfiguration(
            enabled=True,
            required=True,
            hostname="wilsongpt.com",
            certificate_source=CertificateSource.LETS_ENCRYPT,
            certificate_configured=True,
            hostname_matches_certificate=True,
        ),
        dns=DNSReadinessConfiguration(
            hostname="wilsongpt.com",
            dns_provider="manual",
            expected_public_ip="203.0.113.42",
            dns_configured=True,
            dns_matches_expected_target=True,
        ),
        lets_encrypt=LetsEncryptReadinessConfiguration(
            hostname="wilsongpt.com",
            acme_account_configured=True,
            http_01_ready=True,
            renewal_strategy_configured=True,
            certificate_issuance_requested=False,
        ),
        firewall=FirewallReadinessConfiguration(
            inbound_ports_required=[80, 443],
            exposed_ports=[443],
            tls_required=True,
            reverse_proxy_required=True,
            firewall_changes_applied=False,
        ),
        traffic_monitor=TrafficMonitorConfiguration(
            enabled=True,
            mode=TrafficMonitorMode.RECOMMEND_BLOCK,
            signals=[
                TrafficSignalType.FAILED_AUTH,
                TrafficSignalType.REPEATED_401,
                TrafficSignalType.REPEATED_403,
                TrafficSignalType.REPEATED_500,
                TrafficSignalType.SUSPICIOUS_USER_AGENT,
                TrafficSignalType.MALFORMED_REQUEST,
            ],
        ),
        rate_limit=RateLimitConfiguration(enabled=True, requests_per_minute=60, burst_limit=20, scope="ip_client"),
        network_security=NetworkSecurityConfiguration(rate_limit_enabled=True),
        network_reputation_controls=NetworkReputationControlConfiguration(
            ip_allowlists=["198.51.100.0/24"],
            ip_blocklists=["203.0.113.99"],
            country_controls=["allow:US", "block:RU"],
            asn_controls=["block:AS64500"],
            reputation_provider_hooks=[ReputationProviderHook(provider_name="future-provider", enabled=False)],
            enforcement_enabled=False,
        ),
        scanner=ScannerReadinessConfiguration(),
    )


def test_reputation_readiness():
    assessment = ReputationReadinessService().assess(internet_readiness_config())
    assert assessment.reputation_ready is True
    assert assessment.abuse_response_ready is True
    assert assessment.blockers == []


def test_scanner_readiness():
    service = ReputationReadinessService()
    config = internet_readiness_config()
    assert service.assess(config).scanner_ready is True
    config.scanner.anonymous_execution = True
    failed = service.assess(config)
    assert failed.scanner_ready is False
    assert "scanner_readiness_failed" in failed.blockers


def test_endpoint_reputation():
    assessment = ReputationReadinessService().assess(internet_readiness_config())
    assert assessment.endpoint_reputation_ready is True
    assert assessment.authentication_reputation_ready is True


def test_dns_readiness():
    config = internet_readiness_config()
    assessment = ReputationReadinessService().assess(config)
    assert assessment.dns_ready is True
    assert config.dns.hostname == "wilsongpt.com"
    assert config.dns.expected_public_ip == "203.0.113.42"


def test_lets_encrypt_readiness():
    config = internet_readiness_config()
    assessment = ReputationReadinessService().assess(config)
    assert assessment.lets_encrypt_ready is True
    assert config.lets_encrypt.certificate_issuance_requested is False


def test_traffic_monitor_readiness():
    config = internet_readiness_config()
    assessment = ReputationReadinessService().assess(config)
    assert assessment.traffic_monitor_ready is True
    assert config.traffic_monitor.mode == TrafficMonitorMode.RECOMMEND_BLOCK
    assert config.traffic_monitor.can_authorize_access is False


def test_rate_limit_readiness():
    config = internet_readiness_config()
    assessment = ReputationReadinessService().assess(config)
    assert assessment.rate_limit_ready is True
    assert config.rate_limit.enabled is True
    assert config.rate_limit.scope == "ip_client"


def test_network_reputation_controls():
    config = internet_readiness_config()
    assessment = ReputationReadinessService().assess(config)
    assert assessment.network_reputation_ready is True
    assert config.network_reputation_controls.enforcement_enabled is False
    assert config.network_reputation_controls.configured is True


def test_firewall_readiness():
    config = internet_readiness_config()
    assessment = ReputationReadinessService().assess(config)
    assert assessment.firewall_ready is True
    assert config.firewall.exposed_ports == [443]
    assert config.firewall.firewall_changes_applied is False


def test_internet_readiness_gate():
    gate = ReputationReadinessService().internet_gate(internet_readiness_config())
    assert gate.technical_foundation_ready is True
    assert gate.lan_exposure_ready is True
    assert gate.internet_exposure_ready is False
    assert gate.reputation_ready is True
    assert gate.dns_ready is True
    assert gate.tls_reputation_ready is True
    assert gate.abuse_response_ready is True


def test_smoke_profile():
    profile = RegressionProfileService().get(RegressionProfileName.SMOKE)
    assert profile.name == RegressionProfileName.SMOKE
    assert "scripts/Smoke/smoke_16_2_internet_readiness_reputation_validation.py" in profile.test_targets


def test_focused_profile():
    profile = RegressionProfileService().get("focused")
    assert profile.sprint_scoped is True
    assert "tests/test_sprint_16_2_internet_readiness_reputation_validation.py" in profile.test_targets
    assert "reputation" in profile.protects


def test_regression_core_profile():
    profile = RegressionProfileService().get(RegressionProfileName.REGRESSION_CORE)
    assert "governance" in profile.protects
    assert "trust" in profile.protects
    assert "authorization" in profile.protects
    assert "audit" in profile.protects
    assert "repository_boundaries" in profile.protects


def test_regression_full_profile():
    profile = RegressionProfileService().get(RegressionProfileName.REGRESSION_FULL)
    assert profile.test_targets == ["tests"]
    assert profile.protects == ["all"]
