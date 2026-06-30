from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from models.agent_role import AgentRole
from models.devjob import DevJob
from models.worker_context import WorkerContext
from services.devjob_lifecycle_service import DEVWORKER_ROLES
from services.devjob_registry_service import DevJobRegistryService
from services.architecture_work_context_service import ArchitectureWorkContextService
from services.git_service import GitService
from services.patch_registry_service import PatchRegistryService


@dataclass
class DevWorkerContext:
    """Immutable execution context bundle for a single governed DevWorker run."""

    job: DevJob
    workctx: dict[str, Any]
    guidance_context: dict[str, Any]
    evidence: list[dict[str, Any]]
    allowed_paths: list[str]
    prohibited_paths: list[str]


@dataclass
class DevWorkerExecutionResult:
    """Outcome record from a governed DevWorker execution. Reference-only."""

    status: str  # "submitted" | "blocked"
    job_id: str = ""
    patch_id: str | None = None
    artifact_ids: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class DevWorkerExecutionService:
    """
    Governed execution engine for the DevWorker flow.

    Implements exactly the required execution flow:
      Assigned DEVJOB → Load DevJob → Verify assignment → Load WORKCTX
      → Load Guidance Context → Load referenced Evidence
      → Load authorized repository scope → Perform implementation
      → Generate real git diff → Generate governed Patch Artifact
      → Submit DevJob Result References → Stop

    Authority boundary: assigned CLAUDE_CODE worker only.

    This service does NOT create proposals, assign DevJobs, approve work,
    review work, waive validation, execute validation, apply patches,
    complete DevJobs, or bypass any existing governance boundary.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self._devjob_registry = DevJobRegistryService(self.repo_root)
        self._patch_registry = PatchRegistryService(self.repo_root)
        self._workctx_service = ArchitectureWorkContextService(self.repo_root)
        self._git = GitService(self.repo_root)

    # ------------------------------------------------------------------
    # Steps 1-6: Context loading
    # ------------------------------------------------------------------

    def load_context(
        self,
        job_id: str,
        *,
        worker_id: str,
        actor_role: AgentRole,
    ) -> DevWorkerContext:
        """
        Load and verify the DevJob execution context.

        Covers steps 1-6 of the required flow. Raises ValueError on any
        authorization or context failure — no partial context is returned.
        """
        # Step 1: Load DevJob
        try:
            job = self._devjob_registry.get_job(job_id)
        except ValueError as exc:
            raise ValueError(f"devworker_job_load_failed:{exc}") from exc

        # Step 2: Verify assignment
        if actor_role not in DEVWORKER_ROLES:
            raise ValueError(f"devworker_role_not_authorized:{actor_role.value}")
        if job.status not in ("assigned", "in_progress"):
            raise ValueError(f"devworker_job_not_assigned:{job.status}")
        if job.assigned_to != worker_id:
            raise ValueError("devworker_not_assigned_to_this_job")

        # Step 3: Load WORKCTX (required — missing context is a hard stop)
        if not job.work_context_id:
            raise ValueError("devworker_work_context_required")
        try:
            workctx = self._workctx_service.get_package(job.work_context_id)
        except FileNotFoundError as exc:
            raise ValueError("devworker_work_context_missing") from exc

        # Step 4: Load Guidance Context (summary extracted from WORKCTX)
        guidance_context = dict(workctx.get("guidance_context") or {})

        # Step 5: Load referenced Evidence Packages
        evidence: list[dict[str, Any]] = []
        for pkg_id in job.evidence_package_ids:
            pkg_data = self._load_evidence_package(pkg_id)
            if pkg_data is not None:
                evidence.append(pkg_data)

        # Step 6: Load authorized repository scope
        allowed_paths = list(job.allowed_paths or [])
        prohibited_paths = list(job.prohibited_paths or [])

        return DevWorkerContext(
            job=job,
            workctx=workctx,
            guidance_context=guidance_context,
            evidence=evidence,
            allowed_paths=allowed_paths,
            prohibited_paths=prohibited_paths,
        )

    # ------------------------------------------------------------------
    # Path enforcement
    # ------------------------------------------------------------------

    def validate_path(self, path: str, context: DevWorkerContext) -> None:
        """
        Enforce repository path authorization from the DevJob scope.

        Prohibited paths take precedence over allowed paths. If allowed_paths
        is empty, all paths that are not prohibited are permitted.

        Raises ValueError if the path is outside the authorized scope.
        """
        for prohibited in context.prohibited_paths:
            norm = prohibited.rstrip("/")
            if path == prohibited or path.startswith(norm + "/"):
                raise ValueError(f"devworker_path_prohibited:{path}")
        if not context.allowed_paths:
            return
        for allowed in context.allowed_paths:
            norm = allowed.rstrip("/")
            if path == allowed or path.startswith(norm + "/"):
                return
        raise ValueError(f"devworker_path_not_authorized:{path}")

    # ------------------------------------------------------------------
    # Step 8: Diff generation
    # ------------------------------------------------------------------

    def generate_diff(self) -> str:
        """
        Generate real git diff of the current working tree relative to HEAD.

        Returns the unified diff as a string; empty string if no changes.
        """
        try:
            return self._git.diff("HEAD")
        except RuntimeError:
            return self._git.diff()

    # ------------------------------------------------------------------
    # Step 9: Governed patch artifact
    # ------------------------------------------------------------------

    def create_patch_artifact(
        self,
        diff_content: str,
        context: DevWorkerContext,
        *,
        worker_context: WorkerContext | None = None,
    ) -> dict[str, Any]:
        """
        Register the diff as a governed Patch Artifact via PatchRegistryService.

        Returns the patch record summary. Does not apply the patch.
        """
        job = context.job
        ctx = worker_context or WorkerContext(
            worker="DevWorkerExecutionService",
            project_id=job.repo_target or "Ageix",
        )
        return self._patch_registry.create_patch(
            patch_name=f"devjob-{job.job_id}.diff",
            patch_content=diff_content,
            summary=f"Governed patch for DevJob {job.job_id}: {job.title}",
            project_id=job.repo_target or "Ageix",
            worker_context=ctx,
            metadata={
                "job_id": job.job_id,
                "job_title": job.title,
                "work_context_id": job.work_context_id,
                "evidence_package_ids": list(job.evidence_package_ids),
                "allowed_paths": list(job.allowed_paths),
            },
        )

    # ------------------------------------------------------------------
    # Step 10: Result submission
    # ------------------------------------------------------------------

    def submit_result(
        self,
        context: DevWorkerContext,
        patch_id: str,
        *,
        worker_id: str,
        actor_role: AgentRole,
        changed_files: list[str] | None = None,
        artifact_ids: list[str] | None = None,
        validation_run_id: str | None = None,
        result_summary: str = "",
        branch_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit result references for the DevJob (transitions to submitted).

        DevWorker may only move the job to submitted. It may not complete,
        approve, or review the job.
        """
        job = context.job
        if job.status == "assigned":
            self._devjob_registry.transition_job(
                job.job_id,
                "in_progress",
                actor_id=worker_id,
                actor_role=actor_role,
            )
        return self._devjob_registry.submit_result(
            job_id=job.job_id,
            result_summary=result_summary or f"Implementation complete for DevJob {job.job_id}.",
            status="success",
            patch_id=patch_id,
            artifact_ids=list(artifact_ids or []),
            validation_run_id=validation_run_id,
            changed_files=list(changed_files or []),
            branch_name=branch_name,
            submitted_by=worker_id,
            actor_role=actor_role,
        )

    # ------------------------------------------------------------------
    # Full orchestrated flow
    # ------------------------------------------------------------------

    def execute(
        self,
        job_id: str,
        *,
        worker_id: str,
        actor_role: AgentRole,
        implementation_fn: Callable[[DevWorkerContext], list[str]],
    ) -> DevWorkerExecutionResult:
        """
        Orchestrate the complete governed execution flow (Steps 1-10).

        The implementation_fn receives the DevWorkerContext and must:
        - Only write to paths authorized by context.allowed_paths
        - Not write to context.prohibited_paths
        - Return the list of changed file paths

        DevWorker stops after submitting result references. It does not
        complete the DevJob, review it, approve it, or apply the patch.
        """
        # Steps 1-6: Load and verify context
        context = self.load_context(job_id, worker_id=worker_id, actor_role=actor_role)

        # Step 7: Perform implementation (caller-provided)
        changed_files = list(implementation_fn(context) or [])

        # Step 8: Generate real git diff
        diff_content = self.generate_diff()
        if not diff_content.strip():
            return DevWorkerExecutionResult(
                status="blocked",
                job_id=job_id,
                error="devworker_no_changes_detected",
            )

        # Step 9: Generate governed Patch Artifact
        worker_ctx = WorkerContext(
            worker="DevWorkerExecutionService",
            agent_id=worker_id,
            project_id=context.job.repo_target or "Ageix",
        )
        patch = self.create_patch_artifact(diff_content, context, worker_context=worker_ctx)
        patch_id = str(patch["patch_id"])
        artifact_ids = [str(patch["artifact_id"])] if patch.get("artifact_id") else []

        # Step 10: Submit DevJob Result References
        result = self.submit_result(
            context,
            patch_id,
            worker_id=worker_id,
            actor_role=actor_role,
            changed_files=changed_files,
            artifact_ids=artifact_ids,
            result_summary=f"DevWorker completed implementation for DevJob {job_id}.",
        )

        return DevWorkerExecutionResult(
            status="submitted",
            job_id=job_id,
            patch_id=patch_id,
            artifact_ids=artifact_ids,
            changed_files=changed_files,
            result=result,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_evidence_package(self, package_id: str) -> dict[str, Any] | None:
        """Load a single evidence package by ID. Returns None if not found."""
        package_path = (
            self.repo_root / ".ageix" / "evidence_packages" / package_id / "package.json"
        )
        if not package_path.exists():
            return None
        try:
            return json.loads(package_path.read_text(encoding="utf-8"))
        except Exception:
            return None
