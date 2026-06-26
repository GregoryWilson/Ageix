from __future__ import annotations

import shutil
from pathlib import Path
from pprint import pprint

from ageix_mcp.facade_service import MCPFacadeService
from models.proposal import ProposalStatus
from services.architecture_guidance_service import ArchitectureGuidanceService
from services.architecture_registry_service import ArchitectureRegistryService
from services.mcp_context import AgeixRequestContext
from services.proposal_service import ProposalService


def main() -> None:
    root = Path(".ageix_smoke_18_7").resolve()
    if root.exists():
        shutil.rmtree(root)
    try:
        registry = ArchitectureRegistryService(root)
        project = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-18-7-PROJECT", name="Ageix Smoke", node_key="AgeixSmoke", path="AgeixSmoke", node_type="project", description="Smoke project node.")
        domain = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-18-7-DOMAIN", name="Architecture", node_key="Architecture", parent_id=project.architecture_id, node_type="domain", description="Smoke architecture domain.")
        node = registry.create_node(project_id="Ageix_Test", architecture_id="ARCH-SMOKE-18-7", name="Guidance Smoke", node_key="GuidanceSmoke", parent_id=domain.architecture_id, node_type="component", description="Smoke guidance node.")
        context = AgeixRequestContext(session_id="smoke-18-7", agent_id="lex", project_id="Ageix_Test", client_id="chatGPT", provider="chatGPT", authentication_method="dev_token")
        facade = MCPFacadeService(root)
        principle = facade.execute_tool("ageix.architecture.principle.propose", context, {"title": "Smoke principle", "statement": "Architecture guidance proposals remain governed.", "architecture_ids": [node.architecture_id]})
        intent = facade.execute_tool("ageix.architecture.intent.propose", context, {"title": "Smoke intent", "summary": "Architecture guidance should flow into context.", "architecture_ids": [node.architecture_id], "principle_ids": [principle.result["principle_id"]]})
        ProposalService(root).update_status(principle.result["proposal_id"], ProposalStatus.APPROVED)
        ProposalService(root).update_status(intent.result["proposal_id"], ProposalStatus.APPROVED)
        guidance_service = ArchitectureGuidanceService(root)
        guidance_service.accept_approved_principle(principle.result["principle_id"], approved_by="chair")
        guidance_service.accept_approved_intent(intent.result["intent_id"], approved_by="chair")
        guidance = facade.execute_tool("ageix.architecture.guidance", context, {"project_id": "Ageix_Test", "architecture_id": node.architecture_id})
        assert principle.success and principle.result["status"] == "proposed"
        assert intent.success and intent.result["status"] == "proposed"
        assert guidance.success
        assert guidance.result["principle_count"] == 1
        assert guidance.result["intent_count"] == 1
        assert guidance.result["stored_guidance_artifact"] is False
        pprint({"principle_id": principle.result["principle_id"], "intent_id": intent.result["intent_id"], "principle_count": guidance.result["principle_count"], "intent_count": guidance.result["intent_count"]})
        print("Smoke 18.7 PASS: governed principles, intent, derived guidance, MCP proposal, and cleanup validated.")
    finally:
        if root.exists():
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
