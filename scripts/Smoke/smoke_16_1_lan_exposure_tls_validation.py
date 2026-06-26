from __future__ import annotations

from pprint import pprint

from models.public_exposure import (
    CertificateSource,
    DeploymentMode,
    ExposureConfiguration,
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


def build_lan_config() -> ExposureConfiguration:
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
        network_security=NetworkSecurityConfiguration(allowed_ips=["192.168.0.0/16"]),
    )


def main() -> None:
    print("== Smoke 16.1: LAN exposure and TLS validation ==")
    config = build_lan_config()

    print("\n-- LAN deployment validation --")
    pprint(config.topology.model_dump())
    assert config.topology.deployment_mode == DeploymentMode.LAN
    assert config.topology.public_dns_required is False

    print("\n-- exposure policy validation --")
    allowed = ExposurePolicyService().evaluate(config)
    blocked = ExposurePolicyService().evaluate(
        ExposureConfiguration(topology=config.topology, exposure_policy=ExposurePolicy.LOCAL_ONLY)
    )
    pprint({"allowed": allowed.__dict__, "blocked": blocked.__dict__})
    assert allowed.allowed is True
    assert blocked.allowed is False

    print("\n-- TLS self-signed validation --")
    pprint({"ready": config.tls.ready, "tls": config.tls.model_dump()})
    assert config.tls.ready is True
    assert config.tls.certificate_source == CertificateSource.SELF_SIGNED

    print("\n-- reverse proxy template validation --")
    templates = ReverseProxyTemplateService()
    nginx = templates.generate(proxy=config.reverse_proxy, tls=config.tls)
    traefik_config = config.model_copy(deep=True)
    traefik_config.reverse_proxy.provider = ReverseProxyProvider.TRAEFIK
    traefik = templates.generate(proxy=traefik_config.reverse_proxy, tls=traefik_config.tls)
    pprint({
        "primary": nginx.model_dump(exclude={"content"}),
        "secondary": traefik.model_dump(exclude={"content"}),
        "nginx_has_forwarded_headers": "X-Forwarded-For" in nginx.content and "X-Request-ID" in nginx.content,
        "traefik_has_tls": "tls:" in traefik.content,
    })
    assert nginx.provider == ReverseProxyProvider.NGINX
    assert "X-Forwarded-For" in nginx.content
    assert "X-Request-ID" in nginx.content

    print("\n-- forwarded header and correlation validation --")
    headers = ForwardedHeaderContext(
        x_forwarded_for="192.168.1.50",
        x_forwarded_proto="https",
        x_forwarded_host="ageix.local",
        x_request_id="REQ-SMOKE-16-1",
    )
    correlation = RequestCorrelationService().from_forwarded_headers(headers)
    pprint({"headers": headers.model_dump(), "correlation": correlation.model_dump(), "chain": correlation.correlation_chain})
    assert headers.preserves_client_identity is True
    assert correlation.preserved is True

    print("\n-- governance context preservation --")
    context = GovernanceContextSnapshot(
        client_id="chatgpt",
        session_id="smoke-16-1-session",
        project_id="Ageix_Test",
        workflow_id="smoke-16-1-workflow",
        proposal_id="PROP-SMOKE-16-1",
    )
    attached = RequestCorrelationService().attach_to_governance(context=context, correlation=correlation)
    pprint(attached.model_dump())
    assert attached.preserved_through_proxy is True
    assert attached.correlation_id == "audit-REQ-SMOKE-16-1"

    print("\n-- MCP transport validation --")
    mcp = MCPTransportValidation(
        discovery_ok=True,
        invocation_path_ok=True,
        metadata_projection_ok=True,
        governance_protected=True,
        tls_boundary_ok=True,
    )
    pprint(mcp.model_dump() | {"ready": mcp.ready})
    assert mcp.ready is True

    print("\n-- traffic monitor visibility --")
    monitor = TrafficMonitorConfiguration()
    pprint(monitor.model_dump() | {"can_authorize_access": monitor.can_authorize_access})
    assert monitor.can_authorize_access is False

    print("\n-- network security visibility --")
    pprint(config.network_security.model_dump())
    assert config.network_security.allowed_ips == ["192.168.0.0/16"]

    print("\n-- readiness assessment --")
    readiness = PublicReadinessService().assess(config)
    pprint(readiness.model_dump())
    assert readiness.technical_foundation_ready is True
    assert readiness.lan_exposure_ready is True
    assert readiness.internet_exposure_ready is False
    assert readiness.reputation_ready is False

    print("\n-- exposure maturity assessment --")
    maturity = ExposureMaturityService().assess(config)
    pprint(maturity.model_dump())
    assert maturity.current_level.value == "level_1_lan"

    print("\nSmoke 16.1 PASS: LAN exposure path, self-signed TLS, proxy templates, correlation, and governance preservation validated.")


if __name__ == "__main__":
    main()
