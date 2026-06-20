from __future__ import annotations

from dataclasses import dataclass, field

from models.public_exposure import DeploymentMode, ExposureConfiguration, ExposurePolicy


@dataclass(frozen=True)
class ExposurePolicyDecision:
    allowed: bool
    reason: str
    blockers: list[str] = field(default_factory=list)


class ExposurePolicyService:
    """Prevents accidental exposure and preserves Ageix governance authority."""

    def evaluate(self, config: ExposureConfiguration) -> ExposurePolicyDecision:
        blockers: list[str] = []
        mode = config.topology.deployment_mode
        policy = config.exposure_policy

        if policy == ExposurePolicy.LOCAL_ONLY and mode != DeploymentMode.LOCAL:
            blockers.append("local_only_blocks_non_local_deployment")
        if policy == ExposurePolicy.LAN_ONLY and mode == DeploymentMode.INTERNET:
            blockers.append("lan_only_blocks_internet_deployment")
        if mode == DeploymentMode.INTERNET and policy != ExposurePolicy.INTERNET_READY:
            blockers.append("internet_deployment_requires_internet_ready_policy")
        if policy == ExposurePolicy.INTERNET_READY and not config.explicit_public_exposure_intent:
            blockers.append("explicit_public_exposure_intent_required")

        if blockers:
            return ExposurePolicyDecision(False, blockers[0], blockers)
        return ExposurePolicyDecision(True, "exposure_policy_accepted", [])

    def governance_authoritative(self, config: ExposureConfiguration) -> bool:
        # Exposure posture may admit traffic but never grants capability authority.
        return True
