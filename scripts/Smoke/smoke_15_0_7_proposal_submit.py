from pprint import pprint

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-7-proposal-submit",
        project_id="Ageix_Test",
    )

    print("\n== MCP PROPOSAL SUBMISSION ==")

    response = service.execute_tool(
        tool_name="ageix.proposals.submit",
        context=context,
        arguments={
            "objective": "Validate MCP proposal submission path.",
            "proposal_type": "architecture",
            "summary": "Smoke test proposal generated through MCP governed interface.",
        },
    )

    payload = response.model_dump()
    pprint(payload)

    assert payload["success"] is True
    assert payload["errors"] == []

    assert payload["governance"]["authorized"] is True
    assert payload["governance"]["decision"] == "approved"
    assert payload["governance"]["tool_name"] == "ageix.proposals.submit"
    assert payload["governance"]["capability_id"] == "proposal.submit"

    print("\nProposal Result:")
    pprint(payload["result"])

    print(
        "\nSmoke 7 PASS: MCP proposal submission routed through governed proposal capability."
    )


if __name__ == "__main__":
    main()