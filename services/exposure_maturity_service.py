from __future__ import annotations

from models.public_exposure import DeploymentMode, ExposureConfiguration, ExposureMaturityAssessment, ExposureMaturityLevel
from services.public_readiness_service import PublicReadinessService


class ExposureMaturityService:
    """Reports the exposure maturity level without changing network posture."""

    def __init__(self, readiness: PublicReadinessService | None = None) -> None:
        self.readiness = readiness or PublicReadinessService()

    def assess(self, config: ExposureConfiguration, *, target_level: ExposureMaturityLevel = ExposureMaturityLevel.LEVEL_2_INTERNET_READY) -> ExposureMaturityAssessment:
        readiness = self.readiness.assess(config)
        if config.topology.deployment_mode == DeploymentMode.LOCAL:
            level = ExposureMaturityLevel.LEVEL_0_LOCAL
            next_requirements = ["lan_topology", "self_signed_tls", "reverse_proxy_template"]
        elif readiness.lan_exposure_ready:
            level = ExposureMaturityLevel.LEVEL_1_LAN
            next_requirements = ["dns_validation", "lets_encrypt", "reputation_assessment", "firewall_dry_run"]
        elif readiness.technical_foundation_ready:
            level = ExposureMaturityLevel.LEVEL_0_LOCAL
            next_requirements = ["lan_exposure_policy", "reverse_proxy_ready", "tls_ready"]
        else:
            level = ExposureMaturityLevel.LEVEL_0_LOCAL
            next_requirements = readiness.blockers
        return ExposureMaturityAssessment(current_level=level, target_level=target_level, next_requirements=next_requirements)
