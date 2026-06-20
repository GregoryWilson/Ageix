from __future__ import annotations

from pathlib import Path
from typing import Any

from models.evidence_context import EvidenceSelectionEvidence, WorkerContextPackage
from models.work_packet import WorkPacket
from services.code_context_extractor import CodeContextExtractor
from services.controls_service import ControlsService
from services.repository_evidence_service import RepositoryEvidenceService


class EvidenceContextService:
    """Builds worker-specific, budgeted evidence context packages."""

    DEFAULT_CONTEXT_CONTROLS = {
        "mode": "target_scoped",
        "include_full_repo_inventory": False,
        "include_target_files": True,
        "include_impacted_files": True,
        "include_impacted_tests": True,
        "include_dependency_neighbors": True,
        "max_files": 20,
        "max_chars": 30000,
        "overflow_policy": "summarize",
        "code_context_mode": "sliced",
        "allow_full_file_fallback": True,
        "max_slice_lines_per_file": 120,
        "include_imports": True,
        "include_adjacent_helpers": True,
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)
        self.controls = self._load_controls()
        self.extractor = CodeContextExtractor(self.repo_root)

    def build_planner_context(
        self,
        work_packet: WorkPacket,
        *,
        repository_evidence: list[str] | None = None,
        dependency_evidence: dict[str, Any] | None = None,
        impact_evidence: dict[str, Any] | None = None,
    ) -> WorkerContextPackage:
        files = self._candidate_files(work_packet, include_impacted=True, include_dependencies=False)
        selected, excluded = self._apply_file_budget(files)
        summaries = self._repository_summaries(repository_evidence or work_packet.repository_evidence)
        selected_chars = sum(len(item) for item in summaries)
        selection = self._selection_evidence(
            "planner", selected, excluded, selected_chars, 0,
            "Planner receives objective, summaries, relevant inventory, and architectural evidence without code dumps.",
        )
        return WorkerContextPackage(
            worker="planner",
            objective=work_packet.objective,
            summary="Architecture and scope context",
            files={path: self._file_summary(path) for path in selected},
            repository_summaries=summaries,
            impact_summary=impact_evidence or work_packet.impact_summary,
            dependency_summary=dependency_evidence or {},
            acceptance_criteria=work_packet.acceptance_criteria,
            test_targets=work_packet.test_targets,
            approved_scope=work_packet.approved_scope,
            full_repository_inventory_included=self.controls["include_full_repo_inventory"],
            selection_evidence=selection,
        )

    def build_devworker_context(
        self,
        work_packet: WorkPacket,
        *,
        dependency_evidence: dict[str, Any] | None = None,
        impact_evidence: dict[str, Any] | None = None,
    ) -> WorkerContextPackage:
        files = self._approved_scope(work_packet)
        selected, excluded = self._apply_file_budget(files)
        slices, selected_chars, excluded_chars = self._build_code_slices(selected)
        selection = self._selection_evidence(
            "devworker", selected, excluded, selected_chars, excluded_chars,
            "DevWorker receives only approved target files, approved companion tests, relevant slices, imports, and acceptance criteria.",
        )
        return WorkerContextPackage(
            worker="devworker",
            objective=work_packet.objective,
            summary="Implementation-only context",
            files=slices,
            impact_summary=impact_evidence or {"impacted_files": work_packet.impacted_files, "impacted_tests": work_packet.impacted_tests},
            dependency_summary=dependency_evidence or {},
            acceptance_criteria=work_packet.acceptance_criteria,
            test_targets=work_packet.test_targets,
            approved_scope=work_packet.approved_scope,
            selection_evidence=selection,
        )

    def build_validation_context(
        self,
        work_packet: WorkPacket,
        *,
        repository_evidence: list[str] | None = None,
        dependency_evidence: dict[str, Any] | None = None,
        impact_evidence: dict[str, Any] | None = None,
        runtime_evidence: dict[str, Any] | None = None,
    ) -> WorkerContextPackage:
        files = self._candidate_files(work_packet, include_impacted=True, include_dependencies=True)
        selected, excluded = self._apply_file_budget(files)
        selected_chars = sum(len(path) for path in selected)
        selection = self._selection_evidence(
            "validation", selected, excluded, selected_chars, 0,
            "Validation remains authoritative and may use full local repository access plus impact, dependency, and runtime evidence.",
        )
        summary = "Authoritative validation context"
        if runtime_evidence:
            summary += f"; runtime evidence keys: {sorted(runtime_evidence.keys())}"
        return WorkerContextPackage(
            worker="validation",
            objective=work_packet.objective,
            summary=summary,
            files={path: self._file_summary(path) for path in selected},
            repository_summaries=self._repository_summaries(repository_evidence or work_packet.repository_evidence),
            impact_summary=impact_evidence or work_packet.impact_summary,
            dependency_summary=dependency_evidence or {},
            acceptance_criteria=work_packet.acceptance_criteria,
            test_targets=work_packet.test_targets,
            approved_scope=work_packet.approved_scope,
            full_repository_inventory_included=True,
            selection_evidence=selection,
        )

    def build_cloud_context(
        self,
        work_packet: WorkPacket,
        *,
        dependency_evidence: dict[str, Any] | None = None,
        impact_evidence: dict[str, Any] | None = None,
    ) -> WorkerContextPackage:
        files = self._approved_scope(work_packet) + work_packet.impacted_tests[:5]
        selected, excluded = self._apply_file_budget(list(dict.fromkeys(files)))
        slices, selected_chars, excluded_chars = self._build_code_slices(selected)
        selection = self._selection_evidence(
            "cloud", selected, excluded, selected_chars, excluded_chars,
            "Cloud receives compact summaries and relevant slices only; raw graph dumps and full inventories are excluded.",
        )
        return WorkerContextPackage(
            worker="cloud",
            objective=work_packet.objective,
            summary="Compact advisory context",
            files=slices,
            impact_summary=self._compact_impact_summary(impact_evidence or work_packet.impact_summary),
            dependency_summary=self._compact_dependency_summary(dependency_evidence or {}),
            acceptance_criteria=work_packet.acceptance_criteria,
            test_targets=work_packet.test_targets,
            approved_scope=work_packet.approved_scope,
            raw_graphs_included=False,
            full_repository_inventory_included=False,
            selection_evidence=selection,
        )

    def _load_controls(self) -> dict[str, Any]:
        raw = ControlsService(self.repo_root).get_raw_config().get("evidence_context", {})
        merged = dict(self.DEFAULT_CONTEXT_CONTROLS)
        if isinstance(raw, dict):
            merged.update(raw)
        return merged

    def _candidate_files(self, packet: WorkPacket, *, include_impacted: bool, include_dependencies: bool) -> list[str]:
        files = list(packet.target_files)
        if include_impacted:
            files.extend(packet.companion_files)
            files.extend(packet.impacted_tests)
            files.extend(packet.impacted_files)
        if include_dependencies:
            files.extend(packet.repository_evidence)
        return [f for f in dict.fromkeys(files) if isinstance(f, str) and f]

    def _approved_scope(self, packet: WorkPacket) -> list[str]:
        scope = packet.approved_scope or (packet.approved_target_files + packet.approved_companion_tests)
        if not scope:
            scope = packet.target_files
        return [f for f in dict.fromkeys(scope) if isinstance(f, str) and f]

    def _apply_file_budget(self, files: list[str]) -> tuple[list[str], list[str]]:
        max_files = int(self.controls.get("max_files") or 20)
        selected = files[:max_files]
        excluded = files[max_files:]
        return selected, excluded

    def _build_code_slices(self, files: list[str]) -> tuple[dict[str, str], int, int]:
        max_chars = int(self.controls.get("max_chars") or 30000)
        max_lines = int(self.controls.get("max_slice_lines_per_file") or 120)
        selected: dict[str, str] = {}
        selected_chars = 0
        excluded_chars = 0
        for path in files:
            content = self.extractor.extract_file_slice(
                path,
                include_imports=bool(self.controls.get("include_imports", True)),
                include_adjacent_helpers=bool(self.controls.get("include_adjacent_helpers", True)),
                max_lines=max_lines,
                allow_full_file_fallback=bool(self.controls.get("allow_full_file_fallback", True)),
            )
            if not content:
                content = self._file_summary(path)
            if selected_chars + len(content) > max_chars:
                excluded_chars += len(content)
                if self.controls.get("overflow_policy") == "summarize":
                    summary = self._file_summary(path)
                    if selected_chars + len(summary) <= max_chars:
                        selected[path] = summary
                        selected_chars += len(summary)
                continue
            selected[path] = content
            selected_chars += len(content)
        return selected, selected_chars, excluded_chars

    def _file_summary(self, path: str) -> str:
        source = self.repo_root / path
        if source.exists() and source.is_file():
            try:
                text = source.read_text(encoding="utf-8")
                return f"{path}: {len(text.splitlines())} lines, {len(text)} chars"
            except UnicodeDecodeError:
                return f"{path}: binary or non-UTF8 file"
        return f"{path}: referenced file not present locally"

    def _repository_summaries(self, evidence: list[str]) -> list[str]:
        summaries = []
        for item in evidence[: self.controls.get("max_files", 20)]:
            if item.endswith(".py") or "/" in item:
                summaries.append(self._file_summary(item))
            else:
                summaries.append(str(item))
        if not summaries:
            try:
                files = RepositoryEvidenceService(self.repo_root).list_source_files()[:8]
                summaries = [self._file_summary(path) for path in files]
            except Exception:
                summaries = []
        return summaries

    def _compact_impact_summary(self, impact: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(impact, dict):
            return {}
        return {k: v for k, v in impact.items() if k not in {"impact_graph", "raw_graph", "edges"}}

    def _compact_dependency_summary(self, dependency: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(dependency, dict):
            return {}
        return {k: v for k, v in dependency.items() if k not in {"graph", "raw_graph", "edges"}}

    def _selection_evidence(
        self,
        worker: str,
        selected: list[str],
        excluded: list[str],
        selected_chars: int,
        excluded_chars: int,
        reason: str,
    ) -> EvidenceSelectionEvidence:
        return EvidenceSelectionEvidence(
            worker=worker,
            selected_files=selected,
            excluded_files=excluded,
            selected_chars=selected_chars,
            excluded_chars=excluded_chars,
            selection_reason=reason,
            budget_applied=bool(excluded or excluded_chars),
            overflow_policy=str(self.controls.get("overflow_policy", "summarize")),
        )
