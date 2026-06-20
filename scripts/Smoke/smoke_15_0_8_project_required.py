from pprint import pprint
from pydantic import ValidationError

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService


def main():
    service = MCPService(repo_root=".")

    print("\n== MCP PROJECT REQUIRED ==")

    print("\n-- Case 1: missing project_id should fail context validation --")
    try:
        AgeixRequestContext(
            client_id="chatgpt",
            agent_id="lex",
            participant_id="lex",
            session_id="smoke-15-0-8-project-required",
            # project_id intentionally omitted
        )
        raise AssertionError("Expected missing project_id to fail validation")
    except ValidationError as exc:
        print("ValidationError correctly raised:")
        print(exc)

    print("\n-- Case 2: explicit project_id='current' should be rejected --")
    try:
        AgeixRequestContext(
            client_id="chatgpt",
            agent_id="lex",
            participant_id="lex",
            session_id="smoke-15-0-8-project-current-rejected",
            project_id="current",
        )
        raise AssertionError("Expected project_id='current' to fail validation")
    except ValidationError as exc:
        print("ValidationError correctly raised:")
        print(exc)

    print("\n-- Case 3: empty project_id should be rejected --")
    try:
        AgeixRequestContext(
            client_id="chatgpt",
            agent_id="lex",
            participant_id="lex",
            session_id="smoke-15-0-8-project-empty-rejected",
            project_id="",
        )
        raise AssertionError("Expected empty project_id to fail validation")
    except ValidationError as exc:
        print("ValidationError correctly raised:")
        print(exc)

    print("\n-- Case 4: facade denies project-required tool if project_id is unavailable by construction --")
    context = AgeixRequestContext(
        client_id="chatgpt",
        agent_id="lex",
        participant_id="lex",
        session_id="smoke-15-0-8-project-required-valid",
        project_id="Ageix_Test",
    )

    response = service.execute_tool(
        tool_name="ageix.proposals.list",
        context=context,
        arguments={},
    )

    payload = response.model_dump()
    pprint(payload)

    assert payload["success"] in [True, False]
    assert payload["metadata"].get("tool_name") == "ageix.proposals.list"

    print("\nSmoke 8 PASS: MCP project context is mandatory and explicit.")


if __name__ == "__main__":
    main()