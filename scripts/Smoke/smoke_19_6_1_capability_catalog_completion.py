from __future__ import annotations

import json
import sys

from ageix_mcp.tool_definitions import MCP_TOOL_DEFINITIONS
from services.capabilities.patch_capabilities import register_capabilities


def main() -> int:
    print("== Smoke 19.6.1: Capability catalog completion ==")
    tools = {tool.capability_id: tool for tool in MCP_TOOL_DEFINITIONS}
    required_tools = [
        "evidence.request",
        "evidence.proposal.submit",
        "governance.status",
        "agent.list",
        "agent.profile",
        "patch.validate",
        "patch.validation.get",
        "patch.validation.list",
        "patch.ingest",
    ]
    missing = [capability_id for capability_id in required_tools if capability_id not in tools]
    if missing:
        raise AssertionError(f"missing catalog entries: {missing}")

    registered = {definition.capability_id for definition, _handler in register_capabilities(".")}
    for capability_id in ("patch.validate", "patch.validation.get", "patch.validation.list"):
        if capability_id not in registered:
            raise AssertionError(f"missing patch handler: {capability_id}")

    print(json.dumps({
        "required_tool_count": len(required_tools),
        "patch_validate_next": tools["patch.create"].recommended_next_tools,
        "repo_archive_next": tools["repo.archive.create"].recommended_next_tools,
        "evidence_request_tags": tools["evidence.request"].documentation.get("intent_tags", []),
    }, indent=2))
    print("Smoke 19.6.1 PASS: missing capability tools, patch validation handlers, and workflow guidance are exposed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
