from __future__ import annotations

import re

from models.public_exposure import (
    CertificateSource,
    DeploymentMode,
    ExposureConfiguration,
    ExposurePolicy,
    InternetReadinessGate,
    ReputationReadinessAssessment,
    TrafficMonitorMode,
    TrafficSignalType,
)
from services.endpoint_inventory_service import EndpointInventoryService
from services.public_readiness_service import PublicReadinessService


class ReputationReadinessService:
    """Measures public-Internet reputation readiness without changing exposure or enforcement posture."""

    _HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")

    def __init__(self, public_readiness: PublicReadinessService | None = None, endpoint_inventory: EndpointInventoryService | None = None) -> None:
        self.public_readiness = public_readiness or PublicReadinessService()
        self.endpoint_inventory = endpoint_inventory or EndpointInventoryService()

    def assess(self, config: ExposureConfiguration) -> ReputationReadinessAssessment:
        blockers: list[str] = []
        recommendations: list[str] = []

        dns_ready = self._dns_ready(config, blockers)
        lets_encrypt_ready = self._lets_encrypt_ready(config, blockers)
        firewall_ready = self._firewall_ready(config, blockers)
        traffic_monitor_ready = self._traffic_monitor_ready(config, blockers)
        rate_limit_ready = self._rate_limit_ready(config, blockers)
        network_reputation_ready = self._network_reputation_ready(config, blockers, recommendations)
        scanner_ready = self._scanner_ready(config, blockers)
        endpoint_reputation_ready = self._endpoint_reputation_ready(config, blockers)
        authentication_reputation_ready = self._authentication_reputation_ready(config, blockers)
        tls_reputation_ready = bool(config.tls.enabled and config.tls.required and config.tls.hostname_matches_certificate and lets_encrypt_ready)
        if not tls_reputation_ready:
            blockers.append("tls_reputation_not_ready")

        abuse_response_ready = all([traffic_monitor_ready, rate_limit_ready, network_reputation_ready, config.traffic_monitor.audit_required])
        if not abuse_response_ready:
            blockers.append("abuse_response_not_ready")

        reputation_ready = all([
            tls_reputation_ready,
            endpoint_reputation_ready,
            authentication_reputation_ready,
            abuse_response_ready,
            traffic_monitor_ready,
            rate_limit_ready,
            network_reputation_ready,
            scanner_ready,
            dns_ready,
            lets_encrypt_ready,
            firewall_ready,
        ])

        return ReputationReadinessAssessment(
            tls_reputation_ready=tls_reputation_ready,
            endpoint_reputation_ready=endpoint_reputation_ready,
            authentication_reputation_ready=authentication_reputation_ready,
            abuse_response_ready=abuse_response_ready,
            traffic_monitor_ready=traffic_monitor_ready,
            rate_limit_ready=rate_limit_ready,
            network_reputation_ready=network_reputation_ready,
            scanner_ready=scanner_ready,
            dns_ready=dns_ready,
            lets_encrypt_ready=lets_encrypt_ready,
            firewall_ready=firewall_ready,
            reputation_ready=reputation_ready,
            blockers=sorted(set(blockers)),
            recommendations=sorted(set(recommendations)),
        )

    def internet_gate(self, config: ExposureConfiguration) -> InternetReadinessGate:
        # Sprint 16.2 measures whether the technical foundation is ready while
        # deliberately keeping public exposure intent false. PublicReadinessService
        # correctly blocks INTERNET mode without explicit intent, so use an intented
        # copy only to measure foundation prerequisites, never to authorize exposure.
        foundation_config = config.model_copy(deep=True)
        foundation_config.explicit_public_exposure_intent = True
        public = self.public_readiness.assess(foundation_config)
        reputation = self.assess(config)
        blockers = set(reputation.blockers)
        if config.explicit_public_exposure_intent:
            blockers.add("public_exposure_intent_must_remain_false_for_16_2")
        return InternetReadinessGate(
            technical_foundation_ready=public.technical_foundation_ready,
            lan_exposure_ready=True,
            internet_exposure_ready=False,
            reputation_ready=reputation.reputation_ready,
            dns_ready=reputation.dns_ready,
            tls_reputation_ready=reputation.tls_reputation_ready,
            abuse_response_ready=reputation.abuse_response_ready,
            blockers=sorted(blockers),
        )

    def _hostname_valid(self, hostname: str) -> bool:
        return bool(hostname and self._HOSTNAME_RE.match(hostname) and not hostname.endswith(".local"))

    def _dns_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        ready = all([
            self._hostname_valid(config.dns.hostname),
            bool(config.dns.expected_public_ip),
            config.dns.dns_configured,
            config.dns.dns_matches_expected_target,
        ])
        if not ready:
            blockers.append("dns_readiness_not_validated")
        return ready

    def _lets_encrypt_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        le = config.lets_encrypt
        ready = all([
            self._hostname_valid(le.hostname),
            le.acme_account_configured,
            (le.http_01_ready or le.dns_01_ready),
            le.renewal_strategy_configured,
            not le.certificate_issuance_requested,
        ])
        if not ready:
            blockers.append("lets_encrypt_readiness_not_validated")
        return ready

    def _firewall_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        fw = config.firewall
        ports_ok = set(fw.exposed_ports).issubset({80, 443}) and 443 in fw.exposed_ports
        ready = all([ports_ok, fw.tls_required, fw.reverse_proxy_required, not fw.firewall_changes_applied])
        if not ready:
            blockers.append("firewall_readiness_not_validated")
        return ready

    def _traffic_monitor_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        monitor = config.traffic_monitor
        required = {
            TrafficSignalType.FAILED_AUTH,
            TrafficSignalType.REPEATED_401,
            TrafficSignalType.REPEATED_403,
            TrafficSignalType.REPEATED_500,
            TrafficSignalType.SUSPICIOUS_USER_AGENT,
            TrafficSignalType.MALFORMED_REQUEST,
        }
        ready = all([
            monitor.enabled,
            monitor.mode in {TrafficMonitorMode.OBSERVE_ONLY, TrafficMonitorMode.RECOMMEND_BLOCK},
            required.issubset(set(monitor.signals)),
            monitor.can_authorize_access is False,
            monitor.audit_required,
        ])
        if not ready:
            blockers.append("traffic_monitor_readiness_not_validated")
        return ready

    def _rate_limit_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        rate = config.rate_limit
        ready = all([rate.enabled, rate.requests_per_minute > 0, rate.burst_limit > 0, rate.scope in {"ip", "client", "ip_client"}, config.network_security.rate_limit_enabled])
        if not ready:
            blockers.append("rate_limit_readiness_not_validated")
        return ready

    def _network_reputation_ready(self, config: ExposureConfiguration, blockers: list[str], recommendations: list[str]) -> bool:
        controls = config.network_reputation_controls
        ready = controls.configured and controls.audit_required and not controls.enforcement_enabled
        if not ready:
            blockers.append("network_reputation_controls_not_configured")
        if not controls.reputation_provider_hooks:
            recommendations.append("configure_reputation_provider_hook_before_public_cutover")
        return ready

    def _scanner_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        ready = config.scanner.safe_for_scanners and config.outbound_default_policy.value == "deny"
        if not ready:
            blockers.append("scanner_readiness_failed")
        return ready

    def _endpoint_reputation_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        inventory = self.endpoint_inventory.default_inventory()
        ready = bool(inventory) and all(item.auth_required or not item.governance_required for item in inventory)
        if not ready:
            blockers.append("endpoint_reputation_not_ready")
        return ready

    def _authentication_reputation_ready(self, config: ExposureConfiguration, blockers: list[str]) -> bool:
        ready = config.exposure_policy == ExposurePolicy.INTERNET_READY and config.topology.deployment_mode == DeploymentMode.INTERNET and not config.explicit_public_exposure_intent
        if not ready:
            blockers.append("authentication_reputation_not_ready")
        return ready
