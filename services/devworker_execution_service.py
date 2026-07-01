from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from models.agent_role import AgentRole
from models.devjob import DevJob
from models.execution_warning import ExecutionWarning
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
    loaded_evidence_package_ids: list[str] = field(default_factory=list)
    missing_evidence_package_ids: list[str] = field(default_factory=list)
    warnings: list[ExecutionWarning] = field(default_factory=list)


@dataclass
class DevWorkerExecutionResult:
    """Outcome record from a governed DevWorker execution. Reference-only.

    Carries a structured, audit-friendly execution summary so that no missing,
    skipped, partial, blocked, or warning condition degrades silently.
    """

    status: str  # "submitted" | "blocked"
    job_id: str = ""
    worker_id: str = ""
    work_context_id: str | None = None
    patch_id: str | None = None
    artifact_ids: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    loaded_evidence_package_ids: list[str] = field(default_factory=list)
    missing_evidence_package_ids: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_summary(self) -> dict[str, Any]:
        """Return the structured execution summary. Not an EXEC-* artifact."""
        return {
            "status": self.status,
            "worker_id": self.worker_id,
            "job_id": self.job_id,
            "work_context_id": self.work_context_id,
            "loaded_evidence_package_ids": list(self.loaded_evidence_package_ids),
            "missing_evidence_package_ids": list(self.missing_evidence_package_ids),
            "changed_files": list(self.changed_files),
            "patch_id": self.patch_id,
            "warnings": list(self.warnings),
            "blocked_reason": self.error,
        }


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

    Auditability: every missing, skipped, partial, blocked, or warning
    condition is captured as a structured ExecutionWarning and surfaced
    through the execution summary, DevJob result metadata, and append-only
    DevJob events. Nothing degrades silently.
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

        Covers steps 1-6 of the required flow. Fatal context problems (missing
        DevJob, unauthorized worker, invalid assignment, missing required
        WORKCTX) raise ValueError explicitly — no partial context is returned.

        Non-fatal degradations (a referenced evidence package that is
        unavailable) are recorded as structured warnings and tracked on the
        returned context rather than being silently skipped.
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

        # Step 5: Load referenced Evidence Packages.
        # Missing evidence must never be skipped silently: record a structured
        # warning and track it. Referenced evidence is advisory here — its
        # absence does not fail execution (no existing contract marks it
        # mandatory), but it is always surfaced.
        evidence: list[dict[str, Any]] = []
        loaded_ids: list[str] = []
        missing_ids: list[str] = []
        warnings: list[ExecutionWarning] = []
        for pkg_id in job.evidence_package_ids:
            pkg_data = self._load_evidence_package(pkg_id)
            if pkg_data is not None:
                evidence.append(pkg_data)
                loaded_ids.append(pkg_id)
            else:
                missing_ids.append(pkg_id)
                warnings.append(ExecutionWarning(
                    code="evidence_package_missing",
                    severity="warning",
                    message=f"Referenced evidence package {pkg_id} was unavailable and could not be loaded.",
                    related_object_id=pkg_id,
                    metadata={"job_id": job.job_id, "work_context_id": job.work_context_id},
                ))

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
            loaded_evidence_package_ids=loaded_ids,
            missing_evidence_package_ids=missing_ids,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Path enforcement
    # ------------------------------------------------------------------

    def validate_path(self, path: str, context: DevWorkerContext) -> None:
        """
        Enforce repository path authorization from the DevJob scope.

        Prohibited paths take precedence over allowed paths. If allowed_paths
        is empty, all paths that are not prohibited are permitted.

        Raises ValueError explicitly if the path is outside the authorized
        scope — a prohibited path violation is a fatal, non-silent condition.
        """
        for prohibited in context.prohibited_paths:
            norm = prohibited.rstrip("/")
            if path == prohibited or path.startswith(norm + "/"):
                raise ValueError(f"devworker_path_prohibited:{path}")
        # TODO(worker-admission/scope): empty allowed_paths currently means
        # "any non-prohibited path is permitted" (implicit whole-repo scope).
        # A future policy should require an explicit whole-repo authorization
        # token on the DevJob rather than treating an empty list as consent.
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
    # Diff scope enforcement (Sprint 21.3.1)
    #
    # The actual git diff — not worker-declared changed_files — is authoritative
    # for whether the generated patch is within authorized DevJob scope.
    # ------------------------------------------------------------------

    def extract_diff_paths(self, diff_content: str) -> list[str]:
        """
        Parse the actual changed repository paths from a unified git diff.

        Handles modified, added, deleted, and renamed files, and treats
        `/dev/null` (add/delete side) safely. Paths are returned repo-relative
        with the leading ``a/``/``b/`` markers stripped, de-duplicated, in first
        seen order. For renames, both the old and new path are returned so that
        each side is independently scope-checked.
        """
        paths: list[str] = []
        seen: set[str] = set()

        def _add(raw: str) -> None:
            candidate = raw.strip()
            if not candidate or candidate == "/dev/null":
                return
            if candidate.startswith(("a/", "b/")):
                candidate = candidate[2:]
            # git quotes paths containing unusual characters.
            if len(candidate) >= 2 and candidate[0] == '"' and candidate[-1] == '"':
                candidate = candidate[1:-1]
            # `--- a/path\ttimestamp` style trailers.
            candidate = candidate.split("\t", 1)[0].strip()
            if candidate and candidate != "/dev/null" and candidate not in seen:
                seen.add(candidate)
                paths.append(candidate)

        for line in diff_content.splitlines():
            if line.startswith("--- "):
                _add(line[4:])
            elif line.startswith("+++ "):
                _add(line[4:])
            elif line.startswith("rename from "):
                _add(line[len("rename from "):])
            elif line.startswith("rename to "):
                _add(line[len("rename to "):])

        # Fallback for diffs that carry no ---/+++ or rename lines (e.g. pure
        # mode changes): derive both sides from the `diff --git a/X b/Y` header.
        if not paths:
            for line in diff_content.splitlines():
                if line.startswith("diff --git ") and " b/" in line:
                    rest = line[len("diff --git "):]
                    a_part, b_part = rest.split(" b/", 1)
                    _add(a_part)
                    _add("b/" + b_part)

        return paths

    def validate_diff_scope(self, diff_content: str, context: DevWorkerContext) -> list[str]:
        """
        Independently scope-validate the actual paths present in the diff.

        Applies the existing DevJob path scope rules (`validate_path`) to every
        real changed path. Raises ValueError with an explicit reason if any
        actual path is prohibited or outside `allowed_paths`. Returns the list
        of actual changed paths on success — these are authoritative for patch
        scope, regardless of what the implementation declared.
        """
        actual_paths = self.extract_diff_paths(diff_content)
        for path in actual_paths:
            self.validate_path(path, context)
        return actual_paths

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
                "loaded_evidence_package_ids": list(context.loaded_evidence_package_ids),
                "missing_evidence_package_ids": list(context.missing_evidence_package_ids),
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
        warnings: list[ExecutionWarning] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Submit result references for the DevJob (transitions to submitted).

        Any warnings and the loaded/missing evidence lists are attached to the
        submitted result as structured warnings and result metadata, so a
        successful-with-warnings execution never hides its degradations.

        DevWorker may only move the job to submitted. It may not complete,
        approve, or review the job.
        """
        job = context.job
        effective_warnings = list(warnings if warnings is not None else context.warnings)
        warning_dicts = [w.to_dict() for w in effective_warnings]
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
            warnings=warning_dicts,
            metadata={
                "work_context_id": job.work_context_id,
                "loaded_evidence_package_ids": list(context.loaded_evidence_package_ids),
                "missing_evidence_package_ids": list(context.missing_evidence_package_ids),
                "warning_count": len(warning_dicts),
                **dict(extra_metadata or {}),
            },
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

        Blocked conditions are recorded as an append-only DevJob event so they
        are visible through governed DevJob state even though no result is
        submitted; successful-with-warnings conditions are attached to the
        submitted result. Fatal context problems raise from load_context.
        """
        # Steps 1-6: Load and verify context (fatal problems raise here)
        context = self.load_context(job_id, worker_id=worker_id, actor_role=actor_role)
        warnings = list(context.warnings)

        # Step 7: Perform implementation (caller-provided)
        changed_files = list(implementation_fn(context) or [])

        # Step 8: Generate real git diff
        diff_content = self.generate_diff()
        if not diff_content.strip():
            return self._block(
                context,
                worker_id=worker_id,
                actor_role=actor_role,
                reason="devworker_no_changes_detected",
                changed_files=changed_files,
                warnings=warnings,
            )

        # Step 8b (Sprint 21.3.1): Independently scope-validate the ACTUAL diff
        # paths before any governed artifact is created. Worker-declared
        # changed_files are NOT authoritative — the real diff is. A path
        # outside allowed_paths or inside prohibited_paths blocks execution
        # here, before create_patch_artifact() and submit_result().
        try:
            actual_paths = self.validate_diff_scope(diff_content, context)
        except ValueError as exc:
            code, _, offending = str(exc).partition(":")
            return self._block(
                context,
                worker_id=worker_id,
                actor_role=actor_role,
                reason=code or "devworker_diff_path_out_of_scope",
                changed_files=changed_files,
                warnings=warnings,
                extra_metadata={
                    "offending_path": offending,
                    "actual_diff_paths": self.extract_diff_paths(diff_content),
                    "declared_changed_files": list(changed_files),
                },
            )

        # Reconcile declared changed_files against the authoritative diff paths.
        declared = set(changed_files)
        actual_set = set(actual_paths)
        omitted = sorted(actual_set - declared)
        if omitted:
            # Declared list hides real changes: block — the worker's metadata
            # cannot be trusted to describe the patch it produced.
            return self._block(
                context,
                worker_id=worker_id,
                actor_role=actor_role,
                reason="devworker_changed_files_mismatch",
                changed_files=changed_files,
                warnings=warnings,
                extra_metadata={
                    "omitted_paths": omitted,
                    "actual_diff_paths": list(actual_paths),
                    "declared_changed_files": list(changed_files),
                },
            )
        extra_declared = sorted(declared - actual_set)
        if extra_declared:
            # Declared extra paths that never appear in the diff are advisory:
            # surface a warning but proceed; the actual diff remains authoritative.
            warnings.append(ExecutionWarning(
                code="devworker_changed_files_extra",
                severity="warning",
                message=(
                    f"Declared changed_files include {len(extra_declared)} path(s) "
                    "not present in the actual diff; actual diff paths are authoritative."
                ),
                related_object_id=job_id,
                metadata={"extra_paths": extra_declared, "actual_diff_paths": list(actual_paths)},
            ))

        # Step 9: Generate governed Patch Artifact
        worker_ctx = WorkerContext(
            worker="DevWorkerExecutionService",
            agent_id=worker_id,
            project_id=context.job.repo_target or "Ageix",
        )
        patch = self.create_patch_artifact(diff_content, context, worker_context=worker_ctx)
        patch_id = str(patch["patch_id"])
        artifact_ids = [str(patch["artifact_id"])] if patch.get("artifact_id") else []

        # Step 10: Submit DevJob Result References (warnings ride along).
        # Actual diff paths are the authoritative changed_files; the worker's
        # declared list is retained only as metadata.
        result = self.submit_result(
            context,
            patch_id,
            worker_id=worker_id,
            actor_role=actor_role,
            changed_files=list(actual_paths),
            artifact_ids=artifact_ids,
            result_summary=f"DevWorker completed implementation for DevJob {job_id}.",
            warnings=warnings,
            extra_metadata={"worker_declared_changed_files": list(changed_files)},
        )

        return DevWorkerExecutionResult(
            status="submitted",
            job_id=job_id,
            worker_id=worker_id,
            work_context_id=context.job.work_context_id,
            patch_id=patch_id,
            artifact_ids=artifact_ids,
            changed_files=list(actual_paths),
            loaded_evidence_package_ids=list(context.loaded_evidence_package_ids),
            missing_evidence_package_ids=list(context.missing_evidence_package_ids),
            warnings=[w.to_dict() for w in warnings],
            result=result,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _block(
        self,
        context: DevWorkerContext,
        *,
        worker_id: str,
        actor_role: AgentRole,
        reason: str,
        changed_files: list[str],
        warnings: list[ExecutionWarning],
        extra_metadata: dict[str, Any] | None = None,
    ) -> DevWorkerExecutionResult:
        """Record a blocked execution as an append-only DevJob event and return
        a blocked result carrying the structured summary. Does not change the
        DevJob lifecycle state or authority."""
        job = context.job
        detail = dict(extra_metadata or {})
        all_warnings = list(warnings)
        all_warnings.append(ExecutionWarning(
            code=reason,
            severity="error",
            message=f"DevWorker execution was blocked: {reason}.",
            related_object_id=job.job_id,
            metadata={"work_context_id": job.work_context_id, **detail},
        ))
        warning_dicts = [w.to_dict() for w in all_warnings]
        self._devjob_registry.append_event(
            job_id=job.job_id,
            event_type="execution_blocked",
            summary=f"DevWorker execution blocked: {reason}.",
            reason=reason,
            actor_id=worker_id,
            actor_role=actor_role,
            warnings=warning_dicts,
            metadata={
                "work_context_id": job.work_context_id,
                "loaded_evidence_package_ids": list(context.loaded_evidence_package_ids),
                "missing_evidence_package_ids": list(context.missing_evidence_package_ids),
                "changed_files": list(changed_files),
                **detail,
            },
        )
        return DevWorkerExecutionResult(
            status="blocked",
            job_id=job.job_id,
            worker_id=worker_id,
            work_context_id=job.work_context_id,
            changed_files=list(changed_files),
            loaded_evidence_package_ids=list(context.loaded_evidence_package_ids),
            missing_evidence_package_ids=list(context.missing_evidence_package_ids),
            warnings=warning_dicts,
            error=reason,
        )

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
