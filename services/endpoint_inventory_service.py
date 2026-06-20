from __future__ import annotations

from models.public_exposure import EndpointClassification, EndpointInventoryItem


class EndpointInventoryService:
    """Classifies service endpoints before any public exposure is attempted."""

    def default_inventory(self) -> list[EndpointInventoryItem]:
        return [
            EndpointInventoryItem(path="/health", classification=EndpointClassification.AUTHENTICATED_METADATA, auth_required=True),
            EndpointInventoryItem(path="/capabilities", classification=EndpointClassification.AUTHENTICATED_METADATA, auth_required=True),
            EndpointInventoryItem(path="/projects/current", classification=EndpointClassification.AUTHENTICATED_METADATA, auth_required=True),
            EndpointInventoryItem(path="/mcp", classification=EndpointClassification.GOVERNANCE_PROTECTED, auth_required=True, governance_required=True, methods=["POST"]),
            EndpointInventoryItem(path="/internal/audit", classification=EndpointClassification.INTERNAL_ONLY, auth_required=True, governance_required=True, internet_allowed=False),
        ]

    def inventory(self) -> list[dict[str, object]]:
        return [item.model_dump() for item in self.default_inventory()]

    def internet_allowed(self) -> list[EndpointInventoryItem]:
        return [item for item in self.default_inventory() if item.internet_allowed]
