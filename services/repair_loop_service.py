from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from services.repair_execution_service import RepairExecutionService
    from services.cloud_repair_context_builder import CloudRepairContextBuilder
    from services.cloud_repair_service import CloudRepairService

from services.controls_service import ControlsService
from services.governance_policy_service import GovernancePolicyService

MAX_REPAIR_ATTEMPTS = 3


class RepairLoopService:
    def __init__(
        self,
        repo_root: Path | str = ".",
        repair_execution_service: "RepairExecutionService | None" = None,
        cloud_repair_context_builder: "CloudRepairContextBuilder | None" = None,
        cloud_repair_service: "CloudRepairService | None" = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.controls = ControlsService(self.repo_root)
        self.governance = GovernancePolicyService(
            repo_root=self.repo_root,
            controls_service=self.controls,
        )

        if repair_execution_service is None:
            from services.repair_execution_service import RepairExecutionService

            repair_execution_service = RepairExecutionService(repo_root=self.repo_root)

        if cloud_repair_context_builder is None:
            from services.cloud_repair_context_builder import CloudRepairContextBuilder

            cloud_repair_context_builder = CloudRepairContextBuilder()

        if cloud_repair_service is None:
            from services.cloud_repair_service import CloudRepairService

            cloud_repair_service = CloudRepairService()

        self.repair_execution_service = repair_execution_service
        self.cloud_repair_context_builder = cloud_repair_context_builder
        self.cloud_repair_service = cloud_repair_service
        self.repair_loop_root = self.repo_root / ".ageix" / "repair_loops"

    def run_repair_loop(
        self,
        origin_verification_id: str,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        loop_id = f"repair_loop_{time.strftime('%Y%m%d_%H%M%S')}"
        loop_dir = self.repair_loop_root / loop_id
        loop_dir.mkdir(parents=True, exist_ok=False)

        origin_verification = self._load_verification(origin_verification_id)
        origin_patch_id = origin_verification.get("patch_id")

        effective_max_attempts = (
            max_attempts
            if max_attempts is not None
            else self.governance.maximum_local_repair_attempts()
        )

        manifest: dict[str, Any] = {
            "repair_loop_id": loop_id,
            "status": "running",
            "origin_verification_id": origin_verification_id,
            "origin_patch_id": origin_patch_id,
            "max_attempts": effective_max_attempts,
            "attempts": [],
            "final_action": None,
            "escalation": None,
            "cloud_escalation": None,
        }

        

        self._write_manifest(loop_dir, manifest)

        current_verification_id = origin_verification_id

        try:
            for attempt_number in range(1, effective_max_attempts + 1):
                repair_result = self.repair_execution_service.execute_repair_cycle(
                    current_verification_id
                )

                repair_patch_id = repair_result.get("repair_patch_id")
                repair_verification_id = repair_result.get("repair_verification_id")

                if not repair_patch_id or not repair_verification_id:
                    manifest["attempts"].append(
                        {
                            "attempt_number": attempt_number,
                            "source_verification_id": current_verification_id,
                            "repair_patch_id": repair_patch_id,
                            "verification_id": repair_verification_id,
                            "validation_result": None,
                            "decision": "human_review",
                            "status": "incomplete_repair_attempt",
                            "reason": repair_result.get("reason"),
                        }
                    )
                    manifest["status"] = "complete"
                    manifest["final_action"] = "human_review"
                    self._write_manifest(loop_dir, manifest)
                    return manifest

                self._annotate_repair_verification(
                    repair_verification_id=repair_verification_id,
                    attempt_number=attempt_number,
                    origin_verification_id=origin_verification_id,
                    origin_patch_id=origin_patch_id,
                )

                repair_verification = self._load_verification(repair_verification_id)
                validation_result = str(repair_verification.get("result", "")).upper()

                decision = self._decide_outcome(
                    validation_result=validation_result,
                    attempt_number=attempt_number,
                    max_attempts=effective_max_attempts,
                )

                manifest["attempts"].append(
                    {
                        "attempt_number": attempt_number,
                        "source_verification_id": current_verification_id,
                        "repair_patch_id": repair_patch_id,
                        "verification_id": repair_verification_id,
                        "validation_result": validation_result,
                        "decision": decision,
                    }
                )
                self._write_manifest(loop_dir, manifest)

                if decision == "human_review":
                    manifest["status"] = "complete"
                    manifest["final_action"] = "human_review"
                    self._write_manifest(loop_dir, manifest)
                    return manifest

                if decision == "escalate_repair":
                    manifest["escalation"] = {
                        "attempt_number": attempt_number,
                        "reason": "max_repair_attempts_reached",
                        "recorded_action": "escalate_repair",
                        "routed_to": "cloud_repair",
                    }

                    if not self.governance.may_escalate_to_cloud():
                        manifest["status"] = "complete"
                        manifest["final_action"] = "human_review"
                        manifest["cloud_escalation"] = {
                            "attempted": False,
                            "status": "disabled_by_controls",
                            "reason": "cloud_escalation_disabled",
                            "decision": "human_review",
                        }
                        self._write_manifest(loop_dir, manifest)
                        return manifest

                    cloud_result = self._execute_cloud_escalation(
                        manifest=manifest,
                        latest_validation_report=repair_verification,
                    )

                    manifest["cloud_escalation"] = cloud_result
                    manifest["status"] = "complete"
                    manifest["final_action"] = "human_review"
                    self._write_manifest(loop_dir, manifest)
                    return manifest

                current_verification_id = repair_verification_id

            manifest["status"] = "complete"
            manifest["escalation"] = {
                "reason": "max_repair_attempts_reached",
                "recorded_action": "escalate_repair",
                "routed_to": "cloud_repair",
            }

            if not self.controls.repair.allow_cloud_escalation:
                manifest["status"] = "complete"
                manifest["final_action"] = "human_review"
                manifest["cloud_escalation"] = {
                    "attempted": False,
                    "status": "disabled_by_controls",
                    "reason": "cloud_escalation_disabled",
                    "decision": "human_review",
                }
                self._write_manifest(loop_dir, manifest)
                return manifest

            cloud_result = self._execute_cloud_escalation(
                manifest=manifest,
                latest_validation_report=self._load_verification(current_verification_id),
            )

            manifest["cloud_escalation"] = cloud_result
            manifest["status"] = "complete"
            manifest["final_action"] = "human_review"
            self._write_manifest(loop_dir, manifest)
            return manifest

        except Exception as exc:
            manifest["status"] = "interrupted"
            manifest["final_action"] = "human_review"
            manifest["error"] = str(exc)
            self._write_manifest(loop_dir, manifest)
            raise


    def _execute_cloud_escalation(
        self,
        *,
        manifest: dict[str, Any],
        latest_validation_report: dict[str, Any],
    ) -> dict[str, Any]:
        from services.staging_service import StagingService
        from services.validation_service import ValidationService

        escalation_packet = self.cloud_repair_context_builder.build_packet(
            repair_loop_manifest=manifest,
            repository_evidence=None,
            latest_validation_report=latest_validation_report,
        )

        cloud_result = self.cloud_repair_service.execute_cloud_repair(escalation_packet)

        if cloud_result.get("status") != "proposal_generated":
            return {
                "attempted": True,
                "status": cloud_result.get("status"),
                "reason": cloud_result.get("reason"),
                "repair_patch_id": None,
                "verification_id": None,
                "validation_result": None,
                "decision": "human_review",
            }

        proposal = cloud_result.get("proposal")

        if not isinstance(proposal, dict):
            return {
                "attempted": True,
                "status": "invalid_proposal",
                "reason": "cloud_result_missing_proposal",
                "repair_patch_id": None,
                "verification_id": None,
                "validation_result": None,
                "decision": "human_review",
            }

        if proposal.get("result_type") != "patch_proposal":
            return {
                "attempted": True,
                "status": "invalid_proposal",
                "reason": "cloud_result_not_patch_proposal",
                "repair_patch_id": None,
                "verification_id": None,
                "validation_result": None,
                "decision": "human_review",
            }

        staging_service = StagingService(self.repo_root)
        repair_manifest = staging_service.create_stage_from_patch_proposal(proposal)

        validation_service = ValidationService(self.repo_root)
        repair_validation = validation_service.validate_staged_patch(
            repair_manifest.patch_id,
            validation_commands=[
                "python3 - <<'PY'\n"
                "from scratch.context_loop_test import hello\n"
                "assert hello() == 'hello from Ageix'\n"
                "PY"
            ],
        )

        verification_report = self._load_verification(repair_validation.verification_id)
        validation_result = str(verification_report.get("result", "")).upper()

        return {
            "attempted": True,
            "status": "validated",
            "reason": None,
            "repair_patch_id": repair_manifest.patch_id,
            "verification_id": repair_validation.verification_id,
            "validation_result": validation_result,
            "decision": "human_review",
        }

    def _decide_outcome(
        self,
        validation_result: str,
        attempt_number: int,
        max_attempts: int,
    ) -> str:
        if validation_result == "PASS":
            return "human_review"

        if attempt_number >= max_attempts:
            return "escalate_repair"

        return "continue_repair"

    def _load_verification(self, verification_id: str) -> dict[str, Any]:
        candidates = [
            self.repo_root / ".ageix" / "verification" / verification_id / "report.json",
            self.repo_root / ".ageix" / "verification" / verification_id / "verification.json",
            self.repo_root / ".ageix" / "verification" / f"{verification_id}.json",
        ]

        for path in candidates:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError(f"Expected JSON object in {path}")
                return data

        raise FileNotFoundError(f"Verification artifact not found: {verification_id}")

    def _verification_report_path(self, verification_id: str) -> Path:
        path = self.repo_root / ".ageix" / "verification" / verification_id / "report.json"
        if not path.exists():
            raise FileNotFoundError(f"Verification report not found: {path}")
        return path

    def _annotate_repair_verification(
        self,
        *,
        repair_verification_id: str,
        attempt_number: int,
        origin_verification_id: str,
        origin_patch_id: str | None,
    ) -> None:
        report_path = self._verification_report_path(repair_verification_id)
        report = json.loads(report_path.read_text(encoding="utf-8"))

        report["repair_attempt"] = attempt_number
        report["origin_verification_id"] = origin_verification_id
        report["origin_patch_id"] = origin_patch_id

        metadata = report.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        metadata["repair_attempt"] = attempt_number
        metadata["origin_verification_id"] = origin_verification_id
        metadata["origin_patch_id"] = origin_patch_id

        report["metadata"] = metadata

        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def _write_manifest(self, loop_dir: Path, manifest: dict[str, Any]) -> None:
        path = loop_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")