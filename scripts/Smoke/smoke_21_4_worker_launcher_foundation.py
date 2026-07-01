"""
Smoke test: Worker Launcher Foundation (Sprint 21.4, PROP-934ADA8E57B8)

Demonstrates the governed manual launch handoff workflow:

  Admission Ticket -> Launch Profile -> Launch Artifact

Shows that Ageix can convert a valid admission-style launch request into a
governed launch handoff artifact that preserves project context, authority
scope, denied actions, handoff instructions, and traceability — WITHOUT
implying downstream work was executed. Ageix remains the authoritative store.
"""
from __future__ import annotations

# Allow running from the repo root without PYTHONPATH=. (mirrors other smokes).
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import tempfile
from pathlib import Path

from models.agent_role import AgentRole
from services.artifact_registry_service import ArtifactRegistryService
from services.devjob_registry_service import DevJobRegistryService
from services.worker_admission_service import WorkerAdmissionService
from services.worker_launcher_service import WorkerLauncherService

GOV_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
WORKER_ID = "claude.code-smoke-worker"
WORKER_ROLE = AgentRole.CLAUDE_CODE
ADAPTER = "claude_code_browser"


def main() -> None:
    print("== Smoke: Worker Launcher Foundation (Sprint 21.4, PROP-934ADA8E57B8) ==")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        devjobs = DevJobRegistryService(repo)
        admission = WorkerAdmissionService(repo)
        launcher = WorkerLauncherService(repo)

        # Authoritative DevJob assigned to the worker.
        job = devjobs.create_job(
            title="Smoke: implement feature",
            objective="Implement the smoke feature.",
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )
        print(f"Authoritative DevJob: {job.job_id} (status={job.status}, assigned_to={job.assigned_to})")

        # Launch Profile (reused from the Worker Admission foundation).
        profile = admission.create_profile(
            name="Claude Code Web Worker",
            worker_type="claude_code",
            permission_mode="constrained_auto",
            created_by=GOV_ACTOR,
            launch_adapter_hint="claude_code_web",
        )
        print(f"Launch profile: {profile.profile_id} (worker_type={profile.worker_type}, "
              f"permission_mode={profile.permission_mode.value})")

        # Admission Ticket.
        ticket = admission.create_ticket(
            target_type="DEVJOB",
            target_id=job.job_id,
            worker_profile_id=profile.profile_id,
            actor_id=GOV_ACTOR,
            actor_role=CHAIR_ROLE,
        )
        print(f"Admission ticket: {ticket.ticket_id} (status={ticket.status})")

        # ---------------------------------------------------------------
        # Admission Ticket -> Launch Profile -> Launch Artifact
        # ---------------------------------------------------------------
        artifact = launcher.create_launch_artifact(
            admission_ticket_id=ticket.ticket_id,
            adapter=ADAPTER,
            actor_id=GOV_ACTOR,
            actor_role=CHAIR_ROLE,
        )
        print()
        print("--- Governed Launch Handoff Artifact ---")
        print(f"  launch_artifact_id  : {artifact['launch_artifact_id']}")
        print(f"  project_id          : {artifact['project_id']}")
        print(f"  adapter             : {artifact['adapter']}")
        print(f"  target              : {artifact['target_type']} {artifact['target_id']}")
        print(f"  permission_mode     : {artifact['permission_mode']}")
        print(f"  non_authoritative   : {artifact['non_authoritative']}")
        print(f"  execution_performed : {artifact['execution_performed']}")
        print(f"  governed_artifact_id: {artifact['governed_artifact_id']}")
        print("  handoff_instructions:")
        for step in artifact["handoff_instructions"]:
            print(f"    - {step}")
        print(f"  denied_actions      : {artifact['denied_actions']}")
        print(f"  authority_scope     : {artifact['authority_scope']}")
        print(f"  traceability        : {artifact['traceability']}")

        # Assertions: governed handoff, no execution implied.
        assert artifact["project_id"] == "Ageix"
        assert artifact["non_authoritative"] is True
        assert artifact["execution_performed"] is False
        assert artifact["launch_reference"]["authoritative"] is False
        assert artifact["handoff_instructions"]
        assert "direct_worker_execution" in artifact["denied_actions"]
        assert "validation_worker_sequencing" in artifact["denied_actions"]
        assert artifact["authority_scope"]["chair_authority_preserved"] is True
        assert artifact["authority_scope"]["human_execution_boundary"] == "Greg"
        assert artifact["traceability"]["implementation_proposal_id"] == "PROP-934ADA8E57B8"
        assert artifact["traceability"]["authoritative_store"] == "ageix"
        print()
        print("Handoff PASS: governed, non-authoritative launch artifact produced")

        # Registered through the existing governed artifact mechanism.
        governed = ArtifactRegistryService(repo).get_artifact(artifact["governed_artifact_id"])
        assert governed["artifact_type"] == "worker_launch_handoff"
        assert governed["source_id"] == artifact["launch_artifact_id"]
        print(f"Governed artifact PASS: registered as {governed['artifact_id']} "
              f"(type={governed['artifact_type']})")

        # Ageix remains authoritative: DevJob and ticket are untouched.
        job_after = devjobs.get_job(job.job_id)
        ticket_after = admission.get_ticket(ticket.ticket_id)
        assert job_after.status == "assigned"
        assert ticket_after.status == "issued" and ticket_after.redeemed_at is None
        print(f"Authoritative store PASS: DevJob still {job_after.status}, "
              f"ticket still {ticket_after.status} (launcher performed no execution)")

        # A worker cannot mint its own launch handoff (Chair/human boundary).
        try:
            launcher.create_launch_artifact(
                admission_ticket_id=ticket.ticket_id, adapter=ADAPTER,
                actor_id=WORKER_ID, actor_role=WORKER_ROLE,
            )
            raise AssertionError("worker must not create a launch handoff")
        except ValueError as exc:
            assert "worker_launcher_requires_governance" in str(exc)
        print("Governance PASS: worker cannot create a launch handoff")

        # Unknown adapter is denied, not guessed.
        try:
            launcher.create_launch_artifact(
                admission_ticket_id=ticket.ticket_id, adapter="vscode_desktop",
                actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
            )
            raise AssertionError("unknown adapter must be denied")
        except ValueError as exc:
            assert "worker_launcher_adapter_not_supported" in str(exc)
        print("Adapter scope PASS: unsupported adapter denied")

        devjobs.delete_job(job.job_id)

    print()
    print("Smoke PASS: Ageix converts a valid admission-style launch request into a")
    print("governed launch handoff artifact (Admission Ticket -> Launch Profile ->")
    print("Launch Artifact) without implying downstream work was executed.")


if __name__ == "__main__":
    main()
