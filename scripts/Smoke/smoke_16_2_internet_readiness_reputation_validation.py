from __future__ import annotations

from pprint import pprint

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


def build_config() -> ExposureConfiguration:
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
        firewall=FirewallReadinessConfiguration(exposed_ports=[443], firewall_changes_applied=False),
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


def main() -> None:
    print("== Smoke 16.2: Internet readiness and reputation validation ==")
    config = build_config()
    service = ReputationReadinessService()

    print("\n-- DNS readiness --")
    pprint(config.dns.model_dump() | {"ready": service.assess(config).dns_ready})
    assert service.assess(config).dns_ready is True

    print("\n-- TLS reputation and Let's Encrypt readiness --")
    assessment = service.assess(config)
    pprint({
        "tls_reputation_ready": assessment.tls_reputation_ready,
        "lets_encrypt_ready": assessment.lets_encrypt_ready,
        "tls": config.tls.model_dump(),
        "lets_encrypt": config.lets_encrypt.model_dump(),
    })
    assert assessment.tls_reputation_ready is True
    assert assessment.lets_encrypt_ready is True
    assert config.lets_encrypt.certificate_issuance_requested is False

    print("\n-- Firewall readiness --")
    pprint(config.firewall.model_dump() | {"ready": assessment.firewall_ready})
    assert assessment.firewall_ready is True
    assert config.firewall.firewall_changes_applied is False

    print("\n-- Traffic monitoring readiness --")
    pprint(config.traffic_monitor.model_dump() | {"ready": assessment.traffic_monitor_ready, "can_authorize_access": config.traffic_monitor.can_authorize_access})
    assert assessment.traffic_monitor_ready is True
    assert config.traffic_monitor.can_authorize_access is False

    print("\n-- Rate limit readiness --")
    pprint(config.rate_limit.model_dump() | {"ready": assessment.rate_limit_ready})
    assert assessment.rate_limit_ready is True

    print("\n-- Network reputation readiness --")
    pprint(config.network_reputation_controls.model_dump() | {"ready": assessment.network_reputation_ready})
    assert assessment.network_reputation_ready is True
    assert config.network_reputation_controls.enforcement_enabled is False

    print("\n-- Scanner readiness --")
    pprint(config.scanner.model_dump() | {"ready": assessment.scanner_ready})
    assert assessment.scanner_ready is True

    print("\n-- Internet readiness gate --")
    gate = service.internet_gate(config)
    pprint(gate.model_dump())
    assert gate.technical_foundation_ready is True
    assert gate.lan_exposure_ready is True
    assert gate.internet_exposure_ready is False
    assert gate.reputation_ready is True
    assert gate.dns_ready is True
    assert gate.tls_reputation_ready is True
    assert gate.abuse_response_ready is True

    print("\n-- Regression profile validation --")
    profiles = RegressionProfileService()
    focused = profiles.get(RegressionProfileName.FOCUSED)
    core = profiles.get(RegressionProfileName.REGRESSION_CORE)
    pprint({"focused": focused.model_dump(), "regression_core": core.model_dump()})
    assert "tests/test_sprint_16_2_internet_readiness_reputation_validation.py" in focused.test_targets
    assert "governance" in core.protects
    assert "repository_boundaries" in core.protects

    print("\nSmoke 16.2 PASS: reputation readiness, DNS/TLS/firewall dry-run posture, scanner safety, readiness gate, and focused regression profile validated.")


if __name__ == "__main__":
    main()
