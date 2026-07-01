from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from models.agent_role import AgentRole
from services.chair_delegation_service import ChairDelegationService
from services.devjob_registry_service import DevJobRegistryService
from services.turn_service import TurnService

_CLI_PATH = Path(__file__).resolve().parent.parent / "scripts" / "ageix"


def _load_cli():
    # The CLI is an extensionless executable, so use an explicit source loader.
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("ageix_cli", str(_CLI_PATH))
    spec = importlib.util.spec_from_loader("ageix_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _seed(tmp_path: Path):
    (tmp_path / ".ageix").mkdir(parents=True, exist_ok=True)
    job = DevJobRegistryService(tmp_path).create_job(
        title="Sprint 25.5 work", objective="Do it", created_by="greg",
        status="assigned", assigned_to="lex",
    )
    delegation = ChairDelegationService(tmp_path).create_delegation(
        delegate="lex", allowed_actions=["conversation.directive.submit"],
        actor_id="greg", actor_role=AgentRole.AGEIX_CHAIR, reason="approve",
    )
    return job.job_id, delegation.delegation_id


def _run(cli, argv: list[str]) -> int:
    return cli.main(argv)


def test_cli_authoritative_chair_directive(tmp_path: Path) -> None:
    cli = _load_cli()
    job_id, delegation_id = _seed(tmp_path)
    rc = _run(cli, [
        "--repo", str(tmp_path), "directive", "submit",
        "--conversation", "CONV-CLI0001", "--delegation", delegation_id,
        "--devjob", job_id, "--yes",
    ])
    assert rc == 0
    turns = TurnService(tmp_path).list_turns("CONV-CLI0001")
    assert len(turns) == 1
    assert turns[0]["turn_type"] == "DIRECTIVE"
    assert turns[0]["speaker_agent_role"] == AgentRole.AGEIX_CHAIR.value
    # A durable approval-capture record was written.
    captures = list((tmp_path / ".ageix" / "chair_approvals").glob("*.json"))
    assert captures
    record = json.loads(captures[0].read_text())
    assert record["approver"] == "greg"
    assert record["devjob_id"] == job_id


def test_cli_delegated_directive_consumes_delegation(tmp_path: Path) -> None:
    cli = _load_cli()
    job_id, delegation_id = _seed(tmp_path)
    rc = _run(cli, [
        "--repo", str(tmp_path), "directive", "submit",
        "--conversation", "CONV-CLI0002", "--delegation", delegation_id,
        "--devjob", job_id, "--as", "lex", "--yes",
    ])
    assert rc == 0
    turns = TurnService(tmp_path).list_turns("CONV-CLI0002")
    assert turns[0]["speaker_agent_role"] == AgentRole.LEX.value
    assert turns[0]["chair_delegation_id"] == delegation_id
    assert ChairDelegationService(tmp_path).get_delegation(delegation_id).status == "consumed"


def test_cli_reuse_of_consumed_delegation_fails(tmp_path: Path) -> None:
    cli = _load_cli()
    job_id, delegation_id = _seed(tmp_path)
    argv = [
        "--repo", str(tmp_path), "directive", "submit",
        "--conversation", "CONV-CLI0003", "--delegation", delegation_id,
        "--as", "lex", "--yes",
    ]
    assert _run(cli, argv) == 0
    assert _run(cli, argv) == 1  # second use denied by governance


def test_cli_delegation_create_captures_approval(tmp_path: Path) -> None:
    cli = _load_cli()
    (tmp_path / ".ageix").mkdir(parents=True, exist_ok=True)
    rc = _run(cli, [
        "--repo", str(tmp_path), "delegation", "create",
        "--delegate", "lex", "--reason", "approve 25.5", "--yes",
    ])
    assert rc == 0
    listed = ChairDelegationService(tmp_path).list_delegations(delegate="lex")
    assert listed["total_count"] == 1


def test_cli_directive_missing_delegation_is_reported(tmp_path: Path) -> None:
    cli = _load_cli()
    (tmp_path / ".ageix").mkdir(parents=True, exist_ok=True)
    rc = _run(cli, [
        "--repo", str(tmp_path), "directive", "submit",
        "--conversation", "CONV-CLI0004", "--delegation", "CHAIRDLG-NOPE", "--yes",
    ])
    assert rc == 1


def test_cli_worker_engage_queues_and_transitions(tmp_path: Path) -> None:
    cli = _load_cli()
    job_id, _ = _seed(tmp_path)
    # The seeded DevJob is assigned to "lex"; engage it (no provider -> queued).
    rc = _run(cli, [
        "--repo", str(tmp_path), "worker", "engage",
        "--devjob", job_id, "--directive-turn", "TURN-X", "--yes",
    ])
    assert rc == 0
    from services.worker_execution_bridge_service import WorkerExecutionBridgeService
    executions = WorkerExecutionBridgeService(tmp_path).list_executions(devjob_id=job_id)
    assert executions["total_count"] == 1
    assert DevJobRegistryService(tmp_path).get_job(job_id).status == "in_progress"


def test_cli_directive_submit_with_engage_completes_chain(tmp_path: Path) -> None:
    cli = _load_cli()
    job_id, delegation_id = _seed(tmp_path)
    rc = _run(cli, [
        "--repo", str(tmp_path), "directive", "submit",
        "--conversation", "CONV-CLI0005", "--delegation", delegation_id,
        "--devjob", job_id, "--as", "lex", "--engage", "--yes",
    ])
    assert rc == 0
    # Directive recorded AND worker engaged (queued) -> DevJob advanced.
    assert DevJobRegistryService(tmp_path).get_job(job_id).status == "in_progress"
