from __future__ import annotations

from models.public_exposure import (
    CertificateSource,
    DeploymentMode,
    ExposureConfiguration,
    ExposureMaturityLevel,
    ExposurePolicy,
    ForwardedHeaderContext,
    GovernanceContextSnapshot,
    MCPTransportValidation,
    NetworkSecurityConfiguration,
    ReverseProxyConfiguration,
    ReverseProxyProvider,
    TLSConfiguration,
    TrafficMonitorConfiguration,
)
from services.deployment_topology_service import DeploymentTopologyService
from services.exposure_maturity_service import ExposureMaturityService
from services.exposure_policy_service import ExposurePolicyService
from services.public_readiness_service import PublicReadinessService
from services.request_correlation_service import RequestCorrelationService
from services.reverse_proxy_template_service import ReverseProxyTemplateService


def lan_config() -> ExposureConfiguration:
    return ExposureConfiguration(
        topology=DeploymentTopologyService().for_mode(DeploymentMode.LAN, hostname="ageix.local"),
        exposure_policy=ExposurePolicy.LAN_ONLY,
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
            hostname="ageix.local",
            certificate_source=CertificateSource.SELF_SIGNED,
            certificate_configured=True,
            hostname_matches_certificate=True,
        ),
    )


def test_lan_deployment_mode():
    topology = DeploymentTopologyService().for_mode(DeploymentMode.LAN, hostname="ageix.local")
    assert topology.deployment_mode == DeploymentMode.LAN
    assert topology.bind_host == "0.0.0.0"
    assert topology.reverse_proxy_required is True
    assert topology.tls_required is True
    assert topology.public_dns_required is False


def test_lan_exposure_policy():
    service = ExposurePolicyService()
    config = lan_config()
    assert service.evaluate(config).allowed is True

    config.exposure_policy = ExposurePolicy.LOCAL_ONLY
    denied = service.evaluate(config)
    assert denied.allowed is False
    assert "local_only_blocks_non_local_deployment" in denied.blockers

    config.topology = DeploymentTopologyService().for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com")
    config.exposure_policy = ExposurePolicy.LAN_ONLY
    internet_denied = service.evaluate(config)
    assert internet_denied.allowed is False
    assert "lan_only_blocks_internet_deployment" in internet_denied.blockers


def test_reverse_proxy_template_generation_nginx_primary():
    config = lan_config()
    template = ReverseProxyTemplateService().generate(proxy=config.reverse_proxy, tls=config.tls)
    assert template.provider == ReverseProxyProvider.NGINX
    assert "listen 443 ssl" in template.content
    assert "proxy_set_header X-Forwarded-For" in template.content
    assert "proxy_set_header X-Forwarded-Proto https" in template.content
    assert "proxy_set_header X-Request-ID" in template.content
    assert "proxy_pass http://127.0.0.1:8443" in template.content


def test_reverse_proxy_template_generation_traefik_secondary():
    config = lan_config()
    config.reverse_proxy.provider = ReverseProxyProvider.TRAEFIK
    template = ReverseProxyTemplateService().generate(proxy=config.reverse_proxy, tls=config.tls)
    assert template.provider == ReverseProxyProvider.TRAEFIK
    assert "Host(`ageix.local`)" in template.content
    assert "websecure" in template.content
    assert "http://127.0.0.1:8443" in template.content


def test_forwarded_header_preservation():
    headers = ForwardedHeaderContext(
        x_forwarded_for="192.168.1.50",
        x_forwarded_proto="https",
        x_forwarded_host="ageix.local",
        x_request_id="REQ-16-1",
    )
    assert headers.preserves_client_identity is True
    correlation = RequestCorrelationService().from_forwarded_headers(headers)
    assert correlation.proxy_request_id == "REQ-16-1"
    assert correlation.api_request_id == "REQ-16-1"
    assert correlation.audit_correlation_id == "audit-REQ-16-1"
    assert correlation.preserved is True


def test_tls_validation_self_signed():
    tls = TLSConfiguration(
        enabled=True,
        required=True,
        hostname="ageix.local",
        certificate_source=CertificateSource.SELF_SIGNED,
        certificate_configured=True,
        hostname_matches_certificate=True,
    )
    assert tls.ready is True


def test_tls_hostname_validation():
    tls = TLSConfiguration(
        enabled=True,
        required=True,
        hostname="ageix.local",
        certificate_source=CertificateSource.SELF_SIGNED,
        certificate_configured=True,
        hostname_matches_certificate=False,
    )
    assert tls.ready is False


def test_request_correlation_chain():
    correlation = RequestCorrelationService().from_forwarded_headers(ForwardedHeaderContext(x_request_id="REQ-CHAIN"))
    assert correlation.correlation_chain == ["REQ-CHAIN", "REQ-CHAIN", "gov-REQ-CHAIN", "audit-REQ-CHAIN"]


def test_governance_context_preserved():
    correlation = RequestCorrelationService().from_forwarded_headers(ForwardedHeaderContext(x_request_id="REQ-GOV"))
    context = GovernanceContextSnapshot(
        client_id="chatgpt",
        session_id="session-16-1",
        project_id="Ageix_Test",
        workflow_id="workflow-16-1",
        proposal_id="PROP-16-1",
    )
    attached = RequestCorrelationService().attach_to_governance(context=context, correlation=correlation)
    assert attached.preserved_through_proxy is True
    assert attached.correlation_id == "audit-REQ-GOV"


def test_proxy_does_not_bypass_governance():
    config = lan_config()
    assert ExposurePolicyService().governance_authoritative(config) is True
    assert config.reverse_proxy.ready is True
    assert config.exposure_policy == ExposurePolicy.LAN_ONLY


def test_mcp_transport_through_proxy():
    validation = MCPTransportValidation(
        discovery_ok=True,
        invocation_path_ok=True,
        metadata_projection_ok=True,
        governance_protected=True,
        tls_boundary_ok=True,
    )
    assert validation.ready is True


def test_traffic_monitor_visibility():
    monitor = TrafficMonitorConfiguration()
    dumped = monitor.model_dump()
    assert dumped["mode"] == "observe_only"
    assert dumped["action_policy"] == "audit_only"
    assert monitor.can_authorize_access is False


def test_network_security_visibility():
    network = NetworkSecurityConfiguration(
        allowed_ips=["192.168.1.0/24"],
        blocked_ips=["203.0.113.10"],
        allowed_countries=["US"],
        blocked_asns=["AS64500"],
        reputation_filter_enabled=False,
        rate_limit_enabled=False,
    )
    assert network.allowed_ips == ["192.168.1.0/24"]
    assert network.reputation_filter_enabled is False


def test_readiness_split():
    readiness = PublicReadinessService().assess(lan_config())
    assert readiness.technical_foundation_ready is True
    assert readiness.lan_exposure_ready is True
    assert readiness.internet_exposure_ready is False
    assert readiness.reputation_ready is False
    assert readiness.dns_ready is True


def test_exposure_maturity_assessment():
    maturity = ExposureMaturityService().assess(lan_config())
    assert maturity.current_level == ExposureMaturityLevel.LEVEL_1_LAN
    assert maturity.target_level == ExposureMaturityLevel.LEVEL_2_INTERNET_READY
    assert "dns_validation" in maturity.next_requirements
    assert "reputation_assessment" in maturity.next_requirements
