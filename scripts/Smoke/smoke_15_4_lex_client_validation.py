#!/usr/bin/env python3
"""Sprint 15.4 Lex MCP Client Validation smoke tests.

Run from repo root:
    PYTHONPATH=. python scripts/Smoke/smoke_15_4_lex_client_validation.py
"""

from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint
from uuid import uuid4

from mcp.clients import ChatGPTClientProfile, ChatGPTClientSimulator, MCPClientRegistry
from services.agent_session_service import AgentSessionService
from services.project_profile_service import ProjectProfileService

PROJECT_ID = "Ageix_Test"


def _repo_root() -> Path:
    return Path.cwd().resolve()


def _seed_project(repo_root: Path) -> None:
    try:
        ProjectProfileService(repo_root).register_project(PROJECT_ID, PROJECT_ID, "python", repo_root)
    except Exception as exc:
        if "Project already registered" not in str(exc):
            raise


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def smoke_1_client_registry() -> None:
    print("\n== Smoke 15.4.1: Client registry discovery ==")
    clients = {client["client_id"]: client for client in MCPClientRegistry().list_clients()}
    _assert(clients["chatgpt"]["display_name"] == "Lex", "ChatGPT client should be named Lex")
    _assert(clients["chatgpt"]["enabled"] is True, "Lex client should be enabled")
    _assert(clients["chatgpt"]["primary"] is True, "Lex should be primary")
    _assert(clients["claude"]["placeholder"] is True and clients["claude"]["enabled"] is False, "Claude should be a disabled placeholder")
    pprint(clients)
    print("Smoke 15.4.1 PASS")


def smoke_2_lex_identity_initialization() -> None:
    print("\n== Smoke 15.4.2: Lex identity initialization ==")
    profile = ChatGPTClientProfile.resolve()
    _assert(profile.client_id == "chatgpt", "profile client_id mismatch")
    _assert(profile.display_name == "Lex", "profile display name mismatch")
    _assert(profile.provider == "openai", "profile provider mismatch")
    _assert(profile.governance_expectations["identity_grants_authority"] is False, "identity must not grant authority")
    pprint(profile.to_dict())
    print("Smoke 15.4.2 PASS")


def smoke_3_discovery_consumption(repo_root: Path) -> None:
    print("\n== Smoke 15.4.3: Discovery consumption and snapshot ==")
    simulator = ChatGPTClientSimulator(str(repo_root))
    snapshot = simulator.discovery_snapshot()
    snapshot_path = repo_root / ".ageix" / "instance" / "lex_discovery_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    _assert("proposal.submit" in snapshot["capabilities"], "proposal capability missing from discovery")
    _assert("consultation.submit" in snapshot["capabilities"], "consultation capability missing from discovery")
    _assert("ageix.workflow.current" in snapshot["session_tools"], "workflow session tool missing from snapshot")
    _assert("ageix.identity.current" in snapshot["identity_tools"], "identity tool missing from snapshot")
    pprint({"snapshot_path": str(snapshot_path), "tool_count": snapshot["tool_count"]})
    print("Smoke 15.4.3 PASS")


def smoke_4_to_8_validation(repo_root: Path) -> None:
    print("\n== Smoke 15.4.4-8: Workflow, session, governance, audit, readiness ==")
    session_id = f"smoke-15-4-lex-{uuid4().hex[:8]}"
    result = ChatGPTClientSimulator(str(repo_root)).run_validation(project_id=PROJECT_ID, session_id=session_id)
    session = AgentSessionService(repo_root).require_session(session_id)

    _assert(result.validation["workflow_navigation_succeeded"] is True, "workflow self-navigation failed")
    _assert(result.validation["workflow_hints_consumed"] is True, "workflow hints were not consumed")
    _assert(result.validation["session_continuity_succeeded"] is True, "session continuity failed")
    _assert(session.metadata["client_context"]["client_id"] == "chatgpt", "client context was not persisted")
    _assert(session.metadata["client_context"]["authority_granted"] is False, "client context must not grant authority")
    _assert(result.validation["governance_denials_succeeded"] is True, "governance denials were not preserved")
    _assert(result.validation["audit_continuity_succeeded"] is True, "audit continuity failed")
    _assert(result.readiness["ready"] is True, "readiness assessment failed")

    pprint({
        "session_id": session_id,
        "consumed_workflow_hints": result.consumed_workflow_hints,
        "workflow_stage": session.workflow_stage,
        "active_proposal_id": session.active_proposal_id,
        "active_consultation_ids": session.active_consultation_ids,
        "readiness": result.readiness,
    })
    print("Smoke 15.4.4-8 PASS")


def main() -> None:
    repo_root = _repo_root()
    _seed_project(repo_root)
    smoke_1_client_registry()
    smoke_2_lex_identity_initialization()
    smoke_3_discovery_consumption(repo_root)
    smoke_4_to_8_validation(repo_root)
    print("\nSprint 15.4 Lex MCP Client Validation smoke tests PASS")


if __name__ == "__main__":
    main()
