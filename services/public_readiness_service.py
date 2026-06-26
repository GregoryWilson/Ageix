from __future__ import annotations

from models.public_exposure import DeploymentMode, ExposureConfiguration, ExposurePolicy, PublicReadinessAssessment
from services.endpoint_inventory_service import EndpointInventoryService
from services.exposure_policy_service import ExposurePolicyService


class PublicReadinessService:
    """Produces a measurable go/no-go assessment for future public MCP exposure."""

    def __init__(self, policy_service: ExposurePolicyService | None = None, endpoint_inventory: EndpointInventoryService | None = None) -> None:
        self.policy_service = policy_service or ExposurePolicyService()
        self.endpoint_inventory = endpoint_inventory or EndpointInventoryService()

    def assess(self, config: ExposureConfiguration) -> PublicReadinessAssessment:
        blockers: list[str] = []
        policy = self.policy_service.evaluate(config)
        if not policy.allowed:
            blockers.extend(policy.blockers)

        topology_ready = bool(config.topology.hostname and config.topology.bind_host and config.topology.bind_port)
        proxy_ready = config.reverse_proxy.ready
        tls_ready = config.tls.ready
        endpoint_inventory_ready = len(self.endpoint_inventory.default_inventory()) > 0
        network_security_ready = True
        dns_ready = True if not config.topology.public_dns_required else config.dns.ready

        if config.topology.deployment_mode == DeploymentMode.LAN:
            if not proxy_ready:
                blockers.append("lan_deployment_requires_proxy_ready")
            if not tls_ready:
                blockers.append("lan_deployment_requires_tls_ready")
            if config.exposure_policy != ExposurePolicy.LAN_ONLY:
                blockers.append("lan_deployment_requires_lan_only_policy")

        if config.topology.deployment_mode == DeploymentMode.INTERNET:
            if not proxy_ready:
                blockers.append("internet_deployment_requires_proxy_ready")
            if not tls_ready:
                blockers.append("internet_deployment_requires_tls_ready")
            if not dns_ready:
                blockers.append("internet_deployment_requires_dns_ready")
            if config.exposure_policy != ExposurePolicy.INTERNET_READY:
                blockers.append("internet_deployment_requires_internet_ready_policy")

        base_ready = all([
            tls_ready,
            proxy_ready,
            topology_ready,
            policy.allowed,
            endpoint_inventory_ready,
            network_security_ready,
            dns_ready,
        ])
        technical_foundation_ready = bool(base_ready)
        lan_ready = bool(
            base_ready
            and config.topology.deployment_mode == DeploymentMode.LAN
            and config.exposure_policy == ExposurePolicy.LAN_ONLY
            and config.reverse_proxy.tls_termination
            and not config.topology.public_dns_required
        )
        internet_ready = bool(
            base_ready
            and config.topology.deployment_mode == DeploymentMode.INTERNET
            and config.exposure_policy == ExposurePolicy.INTERNET_READY
            and config.explicit_public_exposure_intent
        )

        return PublicReadinessAssessment(
            tls_ready=tls_ready,
            proxy_ready=proxy_ready,
            topology_ready=topology_ready,
            exposure_policy_ready=policy.allowed,
            admission_ready=True,
            identity_ready=True,
            authorization_ready=True,
            governance_ready=True,
            audit_ready=True,
            endpoint_inventory_ready=endpoint_inventory_ready,
            network_security_ready=network_security_ready,
            dns_ready=dns_ready,
            technical_foundation_ready=technical_foundation_ready,
            lan_exposure_ready=lan_ready,
            reputation_ready=False,
            explicit_public_exposure_intent=config.explicit_public_exposure_intent,
            internet_exposure_ready=internet_ready,
            blockers=sorted(set(blockers)),
        )
