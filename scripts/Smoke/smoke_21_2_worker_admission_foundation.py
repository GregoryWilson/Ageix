"""
Smoke test: Worker Admission Foundation (Sprint 21.2, ADR-0014)

Demonstrates the governed Worker Admission flow for a DEVJOB-* target:

  Create launch profile
  Create DevJob admission ticket
  Redeem ticket successfully
  Reject second redemption (single-use)
  Revive / duplicate stale ticket
  Verify minimal admission response
  Verify DevJob remains authoritative

Worker Admission grants participation, never authority. Ageix remains the
authoritative store: the ticket carries no DevJob payload, and redemption
returns minimal admission context only.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from models.agent_role import AgentRole
from services.devjob_registry_service import DevJobRegistryService
from services.worker_admission_service import WorkerAdmissionService

GOV_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
WORKER_ID = "claude.code-smoke-worker"
WORKER_ROLE = AgentRole.CLAUDE_CODE


def main() -> None:
    print("== Smoke: Worker Admission Foundation (Sprint 21.2, ADR-0014) ==")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        devjobs = DevJobRegistryService(repo)
        admission = WorkerAdmissionService(repo)

        # A governed DevJob assigned to the worker (the authoritative record).
        job = devjobs.create_job(
            title="Smoke: implement feature",
            objective="Implement the smoke feature.",
            created_by="greg",
            status="assigned",
            assigned_to=WORKER_ID,
        )
        print(f"Authoritative DevJob: {job.job_id} (status={job.status}, assigned_to={job.assigned_to})")

        # 1. Create launch profile
        profile = admission.create_profile(
            name="Claude Code Web Worker",
            worker_type="claude_code",
            permission_mode="constrained_auto",
            created_by=GOV_ACTOR,
            launch_adapter_hint="claude_code_web",
        )
        print(f"Created launch profile: {profile.profile_id} "
              f"(permission_mode={profile.permission_mode.value}, hint={profile.launch_adapter_hint})")

        # 2. Create DevJob admission ticket
        ticket = admission.create_ticket(
            target_type="DEVJOB",
            target_id=job.job_id,
            worker_profile_id=profile.profile_id,
            actor_id=GOV_ACTOR,
            actor_role=CHAIR_ROLE,
        )
        print(f"Created admission ticket: {ticket.ticket_id} "
              f"(target={ticket.target_type}:{ticket.target_id}, "
              f"single_use={ticket.single_use}, expires_at={ticket.expires_at})")
        assert ticket.status == "issued"

        # 3. Redeem ticket successfully
        admission_ctx = admission.redeem_ticket(
            ticket_id=ticket.ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE,
        )
        print()
        print("--- Minimal Admission Context (redemption response) ---")
        for key, value in admission_ctx.items():
            print(f"  {key:<28}: {value}")
        assert admission_ctx["admission_ticket_id"] == ticket.ticket_id
        assert admission_ctx["target_id"] == job.job_id
        assert admission_ctx["required_next_capability"] == "devjob.get"
        assert admission_ctx["status"] == "redeemed"

        # Verify minimal admission response: NO DevJob payload leaks.
        for forbidden in ("objective", "instructions", "acceptance_criteria", "allowed_paths", "title"):
            assert forbidden not in admission_ctx, f"admission context leaked DevJob field: {forbidden}"
        print("Minimal response PASS: admission context carries no DevJob payload")

        # 4. Reject second redemption (single-use)
        try:
            admission.redeem_ticket(ticket_id=ticket.ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE)
            raise AssertionError("Second redemption should have been denied")
        except ValueError as exc:
            assert "worker_admission_ticket_already_redeemed" in str(exc)
        print(f"Single-use PASS: second redemption denied ({ticket.ticket_id})")

        # 5. Revive / duplicate stale ticket
        revived = admission.revive_ticket(
            ticket_id=ticket.ticket_id, actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
        )
        print(f"Revived stale ticket: {revived.ticket_id} "
              f"(revived_from={revived.revived_from_ticket_id}, status={revived.status})")
        assert revived.ticket_id != ticket.ticket_id
        assert revived.revived_from_ticket_id == ticket.ticket_id
        assert revived.status == "issued"

        # The revived ticket is independently redeemable.
        revived_ctx = admission.redeem_ticket(
            ticket_id=revived.ticket_id, worker_id=WORKER_ID, actor_role=WORKER_ROLE,
        )
        assert revived_ctx["status"] == "redeemed"
        print(f"Revived ticket redeemed successfully: {revived.ticket_id}")

        # 6. Verify DevJob remains authoritative (untouched by admission).
        after = devjobs.get_job(job.job_id)
        assert after.status == "assigned"
        assert after.assigned_to == WORKER_ID
        assert len(after.lifecycle_history) == len(job.lifecycle_history)
        print(f"Authoritative DevJob unchanged: {after.job_id} "
              f"(status={after.status}, assigned_to={after.assigned_to})")

        # Governance boundary: an unauthorized worker cannot mint tickets.
        try:
            admission.create_ticket(
                target_type="DEVJOB", target_id=job.job_id, worker_profile_id=profile.profile_id,
                actor_id=WORKER_ID, actor_role=WORKER_ROLE,
            )
            raise AssertionError("Worker should not be able to create admission tickets")
        except ValueError as exc:
            assert "worker_admission_ticket_create_requires_governance" in str(exc)
        print("Governance PASS: worker cannot mint admission tickets")

        # Unsupported future target types are denied, not guessed.
        for target_type, target_id in (("CONV", "CONV-ABCDEF123456"), ("INTERACTION", "INTERACTION-ABC123")):
            try:
                admission.create_ticket(
                    target_type=target_type, target_id=target_id, worker_profile_id=profile.profile_id,
                    actor_id=GOV_ACTOR, actor_role=CHAIR_ROLE,
                )
                raise AssertionError(f"{target_type} target should be unsupported")
            except ValueError as exc:
                assert "worker_admission_target_unsupported" in str(exc)
        print("Scope PASS: CONV-* and INTERACTION-* targets denied as unsupported")

    print()
    print("Smoke PASS: Worker Admission foundation issues, redeems, denies, and revives")
    print("governed DEVJOB-* admission tickets without granting authority through the ticket.")


if __name__ == "__main__":
    main()
