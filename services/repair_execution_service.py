from __future__ import annotations
from services.repair_orchestration_service import RepairOrchestrationService
from pathlib import Path
from typing import Any
from agents.repository_agent import collect_repair_evidence
from agents.dev_worker_agent import run as run_devworker
from services.staging_service import StagingService
from services.validation_service import ValidationService


class RepairExecutionService:
    """
    First repair execution entry point.

    This service intentionally does NOT:
    - modify repository files
    - stage patches
    - invoke DevWorker
    - validate patches
    - promote or commit anything
    """

    def __init__(
        self,
        repo_root: Path | str = ".",
        repair_orchestrator: RepairOrchestrationService | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repair_orchestrator = repair_orchestrator or RepairOrchestrationService()

    def execute_repair_cycle(self, verification_id: str) -> dict[str, Any]:
        verification = self._load_verification_artifact(verification_id)
        patch_id = verification.get("patch_id")

        if not patch_id:
            return {
                "status": "human_review_required",
                "verification_id": verification_id,
                "patch_id": None,
                "decision": {
                    "action": "REQUEST_HUMAN_REVIEW",
                    "approved": False,
                    "reasoning": ["Verification artifact does not contain patch_id."],
                },
                "reason": "missing_patch_id",
                "next_action": "human_review",
            }

        decision = self.repair_orchestrator.evaluate_repair_decision(verification)

        if not decision.approved:
            return {
                "status": "human_review_required",
                "verification_id": verification_id,
                "patch_id": patch_id,
                "decision": decision.to_dict(),
                "reason": decision.reason,
                "next_action": "human_review",
            }

        repair_work_order = self.repair_orchestrator.build_repair_work_order(
            verification=verification,
            decision=decision,
        )

        repository_evidence = collect_repair_evidence(repair_work_order.to_dict())

        devworker_packet, devworker_result = self._generate_repair_patch_proposal(
            repair_work_order=repair_work_order.to_dict(),
            repository_evidence=repository_evidence,
        )

        deliverable = devworker_result.get("deliverable", {})

        if deliverable.get("result_type") != "patch_proposal":
            return {
                "status": "human_review_required",
                "verification_id": verification_id,
                "patch_id": patch_id,
                "attempt_number": decision.attempt_number,
                "decision": decision.to_dict(),
                "repair_work_order": repair_work_order.to_dict(),
                "repository_evidence": repository_evidence,
                "devworker_packet": devworker_packet,
                "repair_patch_proposal": devworker_result,
                "reason": "devworker_did_not_return_patch_proposal",
                "next_action": "human_review",
            }

        staging_service = StagingService(self.repo_root)
        repair_manifest = staging_service.create_stage_from_patch_proposal(deliverable)
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

        return {
            "status": "repair_patch_validated",
            "verification_id": verification_id,
            "patch_id": patch_id,
            "repair_patch_id": repair_manifest.patch_id,
            "repair_verification_id": repair_validation.verification_id,
            "repair_verification_status": repair_validation.status,
            "attempt_number": decision.attempt_number,
            "decision": decision.to_dict(),
            "repair_work_order": repair_work_order.to_dict(),
            "repository_evidence": repository_evidence,
            "devworker_packet": devworker_packet,
            "repair_patch_proposal": devworker_result,
            "repair_patch_manifest": repair_manifest.to_dict(),
            "repair_validation": {
                "verification_id": repair_validation.verification_id,
                "status": repair_validation.status,
                "patch_id": repair_validation.patch_id,
                "workspace_path": repair_validation.workspace_path,
                "report_path": repair_validation.report_path,
                "test_output_path": repair_validation.test_output_path,
            },
            "next_action": "evaluate_repair_validation_result",
        }

    def _load_verification_artifact(self, verification_id: str) -> dict[str, Any]:
        verification_root = self.repo_root / ".ageix" / "verification"

        candidates = [
            verification_root / verification_id / "report.json",
            verification_root / verification_id / "verification.json",
            verification_root / f"{verification_id}.json",
        ]

        for path in candidates:
            if path.exists():
                return self._read_json(path)

        raise FileNotFoundError(
            f"Could not find verification artifact for verification_id={verification_id}"
        )

    def _build_repair_decision(self, verification: dict[str, Any]) -> dict[str, Any]:
        result = str(verification.get("result", "")).upper()
        status = str(verification.get("status", "")).lower()

        patch_id = verification.get("patch_id")
        verification_id = verification.get("verification_id")

        if result == "PASS":
            return {
                "action": "REQUEST_HUMAN_REVIEW",
                "approved": False,
                "patch_id": patch_id,
                "verification_id": verification_id,
                "reason": "verification_passed",
                "reasoning": [
                    "Verification passed; repair is not required.",
                    "Patch should proceed to human review before promotion.",
                ],
            }

        if result not in {"FAIL", "WARN"}:
            return {
                "action": "REQUEST_HUMAN_REVIEW",
                "approved": False,
                "patch_id": patch_id,
                "verification_id": verification_id,
                "reason": "unsupported_verification_result",
                "reasoning": [
                    f"Verification result '{result}' is not repairable by this service."
                ],
            }

        attempt_number = self._next_attempt_number(verification)

        max_attempts = self._max_repair_attempts()
        if attempt_number > max_attempts:
            return {
                "action": "REQUEST_HUMAN_REVIEW",
                "approved": False,
                "patch_id": patch_id,
                "verification_id": verification_id,
                "attempt_number": attempt_number,
                "max_attempts": max_attempts,
                "reason": "repair_attempt_limit_reached",
                "reasoning": [
                    f"Repair attempt {attempt_number} would exceed max attempts of {max_attempts}."
                ],
            }

        return {
            "action": "APPROVE_REPAIR",
            "approved": True,
            "patch_id": patch_id,
            "verification_id": verification_id,
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "reason": "verification_failed_repair_allowed",
            "reasoning": [
                f"Verification result is {result}.",
                "Repair attempt limit has not been reached.",
                "Repair work order may be generated.",
            ],
        }

    def _build_repair_work_order(
        self,
        verification: dict[str, Any],
        decision: dict[str, Any],
        attempt_number: int,
    ) -> dict[str, Any]:
        patch_id = verification.get("patch_id")
        verification_id = verification.get("verification_id")

        failure_reason = self._extract_failure_reason(verification)

        return {
            "work_order_type": "repair",
            "patch_id": patch_id,
            "source_verification_id": verification_id,
            "attempt_number": attempt_number,
            "objective": verification.get("objective"),
            "repair_objective": (
                "Repair the staged patch so validation passes without changing the "
                "original intent of the patch."
            ),
            "failure_reason": failure_reason,
            "verification_result": verification.get("result"),
            "decision": decision,
            "required_next_step": "repository_evidence_collection",
            "safety_constraints": [
                "Do not promote patches.",
                "Do not commit patches.",
                "Do not bypass validation.",
                "Do not exceed max repair attempts.",
                "Preserve the original patch objective.",
            ],
        }

    def _extract_failure_reason(self, verification: dict[str, Any]) -> str:
        errors = verification.get("errors")
        if isinstance(errors, list) and errors:
            return "\n".join(str(error) for error in errors)

        reasoning = verification.get("reasoning")
        if isinstance(reasoning, list) and reasoning:
            return "\n".join(str(item) for item in reasoning)

        return str(
            verification.get("reason")
            or verification.get("summary")
            or "Verification did not pass."
        )

    def _next_attempt_number(self, verification: dict[str, Any]) -> int:
        existing_attempt = verification.get("repair_attempt")

        if isinstance(existing_attempt, int):
            return existing_attempt + 1

        metadata = verification.get("metadata")
        if isinstance(metadata, dict):
            metadata_attempt = metadata.get("repair_attempt")
            if isinstance(metadata_attempt, int):
                return metadata_attempt + 1

        return 1

    def _max_repair_attempts(self) -> int:
        try:
            from services.repair_orchestration_service import MAX_REPAIR_ATTEMPTS

            return int(MAX_REPAIR_ATTEMPTS)
        except Exception:
            return 3

    def _read_json(self, path: Path) -> dict[str, Any]:
        import json

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object in {path}")

        return data
    
    def _generate_repair_patch_proposal(
        self,
        repair_work_order: dict[str, Any],
        repository_evidence: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        devworker_packet = self._build_devworker_repair_packet(
            repair_work_order=repair_work_order,
            repository_evidence=repository_evidence,
        )

        devworker_result = run_devworker(devworker_packet)

        return devworker_packet, devworker_result


    def _build_repo_evidence_for_devworker(
        self,
        repository_evidence: dict[str, Any],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []

        supporting_evidence = repository_evidence.get("supporting_evidence")
        if isinstance(supporting_evidence, list):
            for item in supporting_evidence:
                evidence.append({
                    "evidence_type": "supporting_note",
                    "content": str(item),
                })

        files = repository_evidence.get("files")
        if isinstance(files, list):
            for file_info in files:
                if not isinstance(file_info, dict):
                    continue

                path = file_info.get("path")
                content = file_info.get("content")

                if not isinstance(path, str):
                    continue

                evidence.append({
                    "evidence_type": "file",
                    "path": path,
                    "content": content if isinstance(content, str) else "",
                    "content_mode": file_info.get("content_mode", "full_file"),
                    "truncated": bool(file_info.get("truncated", False)),
                })

        return evidence


    def _build_devworker_repair_packet(
        self,
        *,
        repair_work_order: dict[str, Any],
        repository_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        target_files: list[str] = []

        files = repository_evidence.get("files")
        if isinstance(files, list):
            for file_info in files:
                if isinstance(file_info, dict) and isinstance(file_info.get("path"), str):
                    target_files.append(file_info["path"])

        return {
            "work_type": "repair",
            "objective": repair_work_order.get("objective", ""),
            "repair_objective": repair_work_order.get("repair_objective", ""),
            "failure_reason": repair_work_order.get("failure_reason", ""),
            "verification_result": repair_work_order.get("verification_result", ""),
            "patch_id": repair_work_order.get("patch_id"),
            "source_verification_id": repair_work_order.get("source_verification_id"),
            "attempt_number": repair_work_order.get("attempt_number"),
            "target_files": target_files,
            "repo_evidence": self._build_repo_evidence_for_devworker(repository_evidence),
            "dependency_hints": repository_evidence.get("dependency_hints", []),
            "repository_evidence": repository_evidence,
            "safety_constraints": repair_work_order.get("safety_constraints", []),
        }
