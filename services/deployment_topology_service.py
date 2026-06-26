from __future__ import annotations

from models.public_exposure import DeploymentMode, DeploymentTopology


class DeploymentTopologyService:
    """Builds fail-closed topology defaults for local, LAN, and future internet deployment."""

    def default_topology(self) -> DeploymentTopology:
        return DeploymentTopology()

    def for_mode(self, mode: DeploymentMode, *, hostname: str | None = None) -> DeploymentTopology:
        if mode == DeploymentMode.LOCAL:
            return DeploymentTopology(deployment_mode=mode, hostname=hostname or "localhost")
        if mode == DeploymentMode.LAN:
            return DeploymentTopology(
                deployment_mode=mode,
                hostname=hostname or "ageix.local",
                bind_host="0.0.0.0",
                reverse_proxy_required=True,
                tls_required=True,
            )
        return DeploymentTopology(
            deployment_mode=mode,
            hostname=hostname or "wilsongpt.com",
            bind_host="127.0.0.1",
            reverse_proxy_required=True,
            tls_required=True,
            public_dns_required=True,
        )
