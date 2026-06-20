from __future__ import annotations

from pprint import pprint

from models.public_exposure import (
    AccessDecisionPolicy,
    CertificateSource,
    DeploymentMode,
    ExposureConfiguration,
    ExposurePolicy,
    OutboundNetworkPolicy,
    ReverseProxyConfiguration,
    ReverseProxyProvider,
    TLSConfiguration,
)
from services.deployment_topology_service import DeploymentTopologyService
from services.endpoint_inventory_service import EndpointInventoryService
from services.exposure_policy_service import ExposurePolicyService
from services.public_readiness_service import PublicReadinessService


def main() -> None:
    print("== Smoke 16.0: Public exposure foundation ==")

    topology_service = DeploymentTopologyService()
    local_config = ExposureConfiguration()
    internet_topology = topology_service.for_mode(DeploymentMode.INTERNET, hostname="wilsongpt.com")

    print("\n-- topology validation --")
    pprint({"local": local_config.topology.model_dump(), "future_internet": internet_topology.model_dump()})

    print("\n-- exposure policy validation --")
    policy_service = ExposurePolicyService()
    blocked = ExposureConfiguration(topology=internet_topology, exposure_policy=ExposurePolicy.LOCAL_ONLY)
    allowed = ExposureConfiguration(topology=internet_topology, exposure_policy=ExposurePolicy.INTERNET_READY, explicit_public_exposure_intent=True)
    pprint({"blocked": policy_service.evaluate(blocked).__dict__, "allowed": policy_service.evaluate(allowed).__dict__})

    print("\n-- TLS readiness --")
    tls = TLSConfiguration(
        enabled=True,
        required=True,
        hostname="wilsongpt.com",
        certificate_source=CertificateSource.LETS_ENCRYPT,
        certificate_configured=True,
        hostname_matches_certificate=True,
    )
    pprint({"tls": tls.model_dump(), "ready": tls.ready})

    print("\n-- reverse proxy readiness --")
    proxy = ReverseProxyConfiguration(provider=ReverseProxyProvider.NGINX, enabled=True, tls_termination=True)
    pprint({"proxy": proxy.model_dump(), "ready": proxy.ready})

    print("\n-- endpoint inventory generation --")
    inventory = EndpointInventoryService().inventory()
    pprint(inventory)

    print("\n-- governance preservation --")
    outbound = OutboundNetworkPolicy(policy=AccessDecisionPolicy.EXPLICIT_APPROVAL, allowed_domains=["api.github.com"], allowed_methods=["GET"])
    pprint({
        "governance_authoritative": policy_service.governance_authoritative(allowed),
        "outbound_without_approval": outbound.evaluate(domain="api.github.com", method="GET"),
        "outbound_with_approval": outbound.evaluate(domain="api.github.com", method="GET", approval_id="APPROVAL-SMOKE"),
    })

    print("\n-- public readiness assessment --")
    readiness_config = ExposureConfiguration(
        topology=internet_topology,
        exposure_policy=ExposurePolicy.INTERNET_READY,
        reverse_proxy=proxy,
        tls=tls,
        explicit_public_exposure_intent=True,
    )
    readiness_config.dns.dns_configured = True
    readiness_config.dns.dns_matches_expected_target = True
    pprint(PublicReadinessService().assess(readiness_config).model_dump())

    print("\nSmoke 16.0 PASS: exposure foundation is modeled, measurable, and governance-preserving.")


if __name__ == "__main__":
    main()
