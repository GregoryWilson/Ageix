"""MCP client validation profiles, admission policies, and compatibility harnesses."""

from ageix_mcp.clients.client_registry import MCPClientRegistry
from ageix_mcp.clients.chatgpt_client_profile import ChatGPTClientProfile
from ageix_mcp.clients.client_readiness_service import ClientReadinessService
from ageix_mcp.clients.client_admission_policy import MCPClientAdmissionPolicy
from ageix_mcp.clients.client_trust_validator import MCPClientTrustValidator
from ageix_mcp.clients.client_hardening_assessment import MCPClientHardeningAssessmentService

__all__ = [
    "MCPClientRegistry",
    "ChatGPTClientProfile",
    "ChatGPTClientSimulator",
    "ClientReadinessService",
    "MCPClientAdmissionPolicy",
    "MCPClientTrustValidator",
    "MCPClientHardeningAssessmentService",
]


def __getattr__(name: str):
    if name == "ChatGPTClientSimulator":
        from ageix_mcp.clients.chatgpt_client_simulator import ChatGPTClientSimulator

        return ChatGPTClientSimulator
    raise AttributeError(name)
