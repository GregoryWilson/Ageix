from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from models.work_packet import WorkPacket
from services.repository_evidence_service import RepositoryEvidenceService
from services.repository_impact_service import RepositoryImpactService


class PlannerWorkPacketService:
    """Builds deterministic Planner work packets from objective, discovery, and repo patterns."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)

    def build(
        self,
        *,
        objective: str,
        task: dict[str, Any] | None = None,
        planner_data: dict[str, Any] | None = None,
        discovery_resolution: dict[str, Any] | None = None,
        known_files: list[str] | None = None,
    ) -> WorkPacket:
        task = task or {}
        planner_data = planner_data or {}
        known_files = known_files or self._list_repo_files()
        discovery_resolution = discovery_resolution or {}

        explicit_targets = self._merge_strings(
            task.get("target_files", []),
            planner_data.get("target_files", []),
            self._step_target_files(planner_data),
        )
        target_files = self._merge_strings(
            explicit_targets,
            [] if explicit_targets else self._infer_target_files(objective),
        )
        objective_requests_tests = self._objective_requests_tests(objective)
        target_files = self.expand_target_files(
            target_files,
            include_generic_tests=objective_requests_tests,
        )

        impact_result = RepositoryImpactService(self.repo_root).analyze(
            target_files=target_files,
            proposal={"changes": []},
        )
        target_files = self._merge_strings(
            target_files,
            impact_result.companion_files,
            impact_result.impacted_tests,
        )

        test_targets = self._merge_strings(
            planner_data.get("test_targets", []),
            [path for path in target_files if self._is_test_path(path)],
            impact_result.impacted_tests,
        )
        test_commands = self._merge_strings(
            planner_data.get("test_commands", []),
            [f"PYTHONPATH=. python -m pytest {path}" for path in test_targets],
        )

        architecture_constraints = self._merge_strings(
            planner_data.get("architecture_constraints", []),
            self._architecture_constraints(discovery_resolution),
        )
        requirements = self._merge_strings(
            planner_data.get("requirements", []),
            self._requirement_seeds(objective, target_files, discovery_resolution),
        )
        acceptance_criteria = self._merge_strings(
            planner_data.get("acceptance_criteria", []),
            self._acceptance_criteria(target_files, test_targets, requirements),
        )
        implementation_strategy = self._merge_strings(
            planner_data.get("implementation_strategy", []),
            self._research_implications(discovery_resolution),
            architecture_constraints,
            ["Implement only the files authorized by the work packet."],
        )

        repository_evidence = self._merge_strings(
            planner_data.get("repository_evidence", []),
            self.select_repository_examples(target_files, known_files),
        )

        approved_target_files = [path for path in target_files if not self._is_test_path(path)]
        approved_companion_tests = self._merge_strings(
            [path for path in target_files if self._is_test_path(path)],
            impact_result.companion_files,
            impact_result.impacted_tests,
        )
        approved_scope = self._merge_strings(approved_target_files, approved_companion_tests)

        return WorkPacket(
            objective=objective,
            implementation_strategy=implementation_strategy,
            target_files=target_files,
            repository_evidence=repository_evidence,
            requirements=requirements,
            acceptance_criteria=acceptance_criteria,
            test_targets=test_targets,
            test_commands=test_commands,
            architecture_constraints=architecture_constraints,
            discovery_evidence=self._compact_discovery_evidence(discovery_resolution),
            impacted_files=impact_result.impacted_files,
            impacted_tests=impact_result.impacted_tests,
            companion_files=impact_result.companion_files,
            impact_summary=impact_result.summary,
            approved_target_files=approved_target_files,
            approved_companion_tests=approved_companion_tests,
            approved_scope=approved_scope,
        )

    def expand_target_files(
        self,
        target_files: list[str],
        *,
        include_generic_tests: bool = False,
    ) -> list[str]:
        expanded = list(target_files)
        for path in target_files:
            companion = self._companion_test_file(
                path,
                include_generic_tests=include_generic_tests,
            )
            if companion and companion not in expanded:
                expanded.append(companion)
        return sorted(dict.fromkeys(expanded))

    def expand_after_unauthorized_change(
        self,
        *,
        target_files: list[str],
        proposed_file: str,
    ) -> list[str]:
        if self._is_obvious_companion_test(target_files, proposed_file):
            return sorted(set(target_files) | {proposed_file})
        return sorted(dict.fromkeys(target_files))

    def select_repository_examples(self, target_files: list[str], known_files: list[str] | None = None) -> list[str]:
        service = RepositoryEvidenceService(self.repo_root)
        return service.select_evidence_files(
            objective=" ".join(target_files),
            target_files=target_files,
            known_files=known_files or self._list_repo_files(),
            limit=8,
        )

    def _infer_target_files(self, objective: str) -> list[str]:
        text = objective.lower()
        if "jira" in text and "worker" in text:
            return ["agents/jira_worker_agent.py", "services/jira_service.py"]
        return []

    def _step_target_files(self, data: dict[str, Any]) -> list[str]:
        files: list[str] = []
        for step in data.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            files.extend(step.get("target_files") or [])
            inputs = step.get("inputs") if isinstance(step.get("inputs"), dict) else {}
            files.extend(inputs.get("target_files") or [])
        return files

    def _companion_test_file(
        self,
        path: str,
        *,
        include_generic_tests: bool = False,
    ) -> str | None:
        normalized = path.replace("\\", "/")
        if self._is_test_path(normalized) or not normalized.endswith(".py"):
            return None
        name = Path(normalized).stem
        if normalized.startswith("services/"):
            return f"tests/test_{name}.py"
        if normalized.startswith("agents/"):
            if name.endswith("_agent"):
                name = name[:-6]
            return f"tests/test_{name}_agent.py"
        if include_generic_tests:
            return f"tests/test_{name}.py"
        return None

    def _is_obvious_companion_test(self, target_files: list[str], proposed_file: str) -> bool:
        if not self._is_test_path(proposed_file):
            return False
        return proposed_file in [
            self._companion_test_file(path, include_generic_tests=True)
            for path in target_files
        ]

    def _is_test_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return normalized.startswith("tests/") or Path(normalized).name.startswith("test_")

    def _objective_requests_tests(self, objective: str) -> bool:
        lowered = objective.lower()
        test_markers = [
            " test",
            " tests",
            "pytest",
            "unit test",
            "deterministic test",
            "deterministic tests",
            "add tests",
            "with tests",
            "and tests",
        ]
        return any(marker in lowered for marker in test_markers)

    def _requirement_seeds(self, objective: str, target_files: list[str], discovery_resolution: dict[str, Any]) -> list[str]:
        reqs = [f"REQ-001 Implement objective: {objective}"]
        index = 2
        if any(path.startswith("services/") for path in target_files):
            reqs.append(f"REQ-{index:03d} Create or update service boundary")
            index += 1
        if any(path.startswith("agents/") for path in target_files):
            reqs.append(f"REQ-{index:03d} Create or update worker boundary")
            index += 1
        for implication in self._research_implications(discovery_resolution):
            reqs.append(f"REQ-{index:03d} {implication}")
            index += 1
        if any(self._is_test_path(path) for path in target_files) or self._objective_requests_tests(objective):
            reqs.append(f"REQ-{index:03d} Provide deterministic tests")
        return reqs

    def _acceptance_criteria(self, target_files: list[str], test_targets: list[str], requirements: list[str]) -> list[str]:
        criteria = [f"Authorized target file exists in proposal: {path}" for path in target_files]
        criteria.extend(f"Executable test target exists: {path}" for path in test_targets)
        if requirements:
            criteria.append("Requirement trace covers every seeded requirement")
        if test_targets:
            criteria.append("Generated test command passes")
        return criteria

    def _research_implications(self, resolution: dict[str, Any]) -> list[str]:
        implications: list[str] = []
        for result in resolution.get("research_results", []) or []:
            for claim in result.get("claims", []) or []:
                implications.extend(claim.get("implementation_implications", []) or [])
                claim_text = claim.get("claim")
                if claim_text and not claim.get("implementation_implications"):
                    implications.append(claim_text)
            implications.extend(result.get("recommended_patterns", []) or [])
            implications.extend(result.get("dependency_recommendations", []) or [])
        return self._merge_strings(implications)

    def _architecture_constraints(self, resolution: dict[str, Any]) -> list[str]:
        review = resolution.get("architecture_review") or {}
        return self._merge_strings(
            review.get("recommendations", []),
            review.get("preferred_patterns", []),
            review.get("dependency_guidance", []),
        )

    def _compact_discovery_evidence(self, resolution: dict[str, Any]) -> dict[str, Any]:
        if not resolution:
            return {}
        return {
            "status": resolution.get("status"),
            "confidence": resolution.get("confidence", {}),
            "research_claims": [
                claim.get("claim")
                for result in resolution.get("research_results", []) or []
                for claim in result.get("claims", []) or []
                if isinstance(claim, dict) and claim.get("claim")
            ],
            "architecture_approved": (resolution.get("architecture_review") or {}).get("architecture_approved"),
        }

    def _list_repo_files(self) -> list[str]:
        return RepositoryEvidenceService(self.repo_root).list_source_files()

    def _first_matches(self, files: list[str], needles: list[str], *, exclude: list[str], limit: int) -> list[str]:
        matches = []
        for path in files:
            if path in exclude:
                continue
            if all(needle in path for needle in needles):
                matches.append(path)
            if len(matches) >= limit:
                break
        return matches

    def _merge_strings(self, *values: Any) -> list[str]:
        merged: list[str] = []
        for value in values:
            if isinstance(value, str):
                items = [value]
            elif isinstance(value, list):
                items = value
            else:
                items = []
            for item in items:
                if item is None:
                    continue
                text = str(item).strip()
                if text and text not in merged:
                    merged.append(text)
        return merged
