from __future__ import annotations

from models.public_exposure import RegressionProfile, RegressionProfileName


class RegressionProfileService:
    """Defines bounded validation profiles so future sprints can avoid unnecessary full-suite runs."""

    def profiles(self) -> dict[RegressionProfileName, RegressionProfile]:
        return {
            RegressionProfileName.SMOKE: RegressionProfile(
                name=RegressionProfileName.SMOKE,
                description="Current sprint smoke validation only.",
                test_targets=["scripts/Smoke/smoke_16_2_internet_readiness_reputation_validation.py"],
                protects=["current_sprint_behavior"],
                sprint_scoped=True,
            ),
            RegressionProfileName.FOCUSED: RegressionProfile(
                name=RegressionProfileName.FOCUSED,
                description="Sprint-focused unit tests plus smoke validation.",
                test_targets=[
                    "tests/test_sprint_16_2_internet_readiness_reputation_validation.py",
                    "scripts/Smoke/smoke_16_2_internet_readiness_reputation_validation.py",
                ],
                protects=["reputation", "dns", "tls", "traffic", "rate_limits", "scanner_readiness"],
                sprint_scoped=True,
            ),
            RegressionProfileName.REGRESSION_CORE: RegressionProfile(
                name=RegressionProfileName.REGRESSION_CORE,
                description="Core governance, trust, authorization, audit, and repository-boundary protections.",
                test_targets=[
                    "tests/test_sprint_12_capability_interface.py",
                    "tests/test_sprint_14_1_auth_boundary.py",
                    "tests/test_sprint_15_5_mcp_client_trust_boundary.py",
                    "tests/test_sprint_16_0_public_exposure_foundation.py",
                    "tests/test_sprint_16_1_lan_exposure_tls_validation.py",
                    "tests/test_sprint_16_2_internet_readiness_reputation_validation.py",
                ],
                protects=["governance", "trust", "authorization", "audit", "repository_boundaries"],
            ),
            RegressionProfileName.REGRESSION_FULL: RegressionProfile(
                name=RegressionProfileName.REGRESSION_FULL,
                description="Entire pytest suite.",
                test_targets=["tests"],
                protects=["all"],
            ),
        }

    def get(self, name: RegressionProfileName | str) -> RegressionProfile:
        profile_name = name if isinstance(name, RegressionProfileName) else RegressionProfileName(name)
        return self.profiles()[profile_name]
