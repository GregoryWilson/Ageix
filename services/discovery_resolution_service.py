from __future__ import annotations

from pathlib import Path
from typing import Any

from models.architecture_review import ArchitectureReview
from models.discovery import DiscoveryConfidence, DiscoveryResult
from models.discovery_resolution import BlockerLineage, DiscoveryResolutionResult
from models.research import ResearchResult
from services.architecture_review_service import ArchitectureReviewService
from services.discovery_artifact_service import DiscoveryArtifactService
from services.discovery_service import DiscoveryService
from services.research_worker_service import ResearchWorkerService
from services.worker_profile_service import WorkerProfileService


class DiscoveryResolutionService:
    def __init__(
        self,
        repo_root: str | Path = ".",
        discovery_service: DiscoveryService | None = None,
        research_worker: ResearchWorkerService | None = None,
        architecture_review_service: ArchitectureReviewService | None = None,
        artifact_service: DiscoveryArtifactService | None = None,
        profile_service: WorkerProfileService | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.discovery_service = discovery_service or DiscoveryService()
        self.research_worker = research_worker or ResearchWorkerService()
        self.architecture_review_service = architecture_review_service or ArchitectureReviewService()
        self.artifact_service = artifact_service or DiscoveryArtifactService(self.repo_root)
        self.profile_service = profile_service or WorkerProfileService(Path("."))

    def resolve(
        self,
        *,
        objective: str,
        target_files: list[str] | None = None,
        answers: dict[str, Any] | None = None,
        run_id: str | None = None,
        execute_research: bool = True,
        execute_architecture_review: bool = True,
        repository_evidence: list[dict[str, Any]] | None = None,
        persist: bool = False,
    ) -> DiscoveryResolutionResult:
        answers = dict(answers or {})
        target_files = target_files or []
        initial = self.discovery_service.analyze(objective=objective, target_files=target_files, answers=answers)

        research_results: list[ResearchResult] = []
        architecture_review: ArchitectureReview | None = None
        lineage = self._build_lineage(initial)

        needs_research = any(blocker.resolver == "research" for blocker in initial.blockers)
        needs_architecture = any(blocker.resolver == "cloud_architect" for blocker in initial.blockers)

        if needs_research and not execute_research:
            status = "research_pending"
            result = self._result(status, initial, research_results, architecture_review, initial.confidence, lineage)
            if persist and run_id:
                self._persist(run_id, objective, initial, answers, result)
            return result

        if needs_research:
            research_result = self.research_worker.research(
                objective=objective,
                research_topics=self._research_topics(objective, initial),
            )
            research_results.append(research_result)
            answers["research_evidence"] = True
            self._resolve_lineage(lineage, resolver="research", resolved_by="research_worker", evidence_ids=[claim.claim_id for claim in research_result.claims])

        rediscovered = self.discovery_service.analyze(objective=objective, target_files=target_files, answers=answers)
        needs_architecture = any(blocker.resolver == "cloud_architect" for blocker in rediscovered.blockers)

        if needs_architecture and not execute_architecture_review:
            status = "architecture_pending"
            result = self._result(status, rediscovered, research_results, architecture_review, rediscovered.confidence, lineage)
            if persist and run_id:
                self._persist(run_id, objective, rediscovered, answers, result)
            return result

        if needs_architecture or rediscovered.architecture.review_recommended:
            architecture_review = self.architecture_review_service.review(
                objective=objective,
                repository_evidence=repository_evidence or [],
                research_results=research_results,
                user_answers=answers,
            )
            if architecture_review.architecture_approved:
                answers["architecture_review"] = "approved"
                self._resolve_lineage(lineage, resolver="cloud_architect", resolved_by="cloud_architect", evidence_ids=["architecture_review"])

        final_discovery = self.discovery_service.analyze(objective=objective, target_files=target_files, answers=answers)
        confidence = self.recalculate_confidence(final_discovery, research_results, architecture_review)
        status = "ready_for_planning" if self._planner_unlocked(final_discovery, confidence, research_results, architecture_review) else "discovery_required"
        result = self._result(status, final_discovery, research_results, architecture_review, confidence, lineage)
        if persist and run_id:
            self._persist(run_id, objective, final_discovery, answers, result)
        return result

    def recalculate_confidence(
        self,
        discovery: DiscoveryResult,
        research_results: list[ResearchResult],
        architecture_review: ArchitectureReview | None,
    ) -> DiscoveryConfidence:
        external_api = discovery.confidence.external_api
        if research_results:
            external_api = max(external_api, max(item.confidence for item in research_results))
        architecture = discovery.confidence.architecture
        if architecture_review is not None:
            architecture = max(architecture, architecture_review.confidence)
        dependency = discovery.confidence.dependency
        if architecture_review and architecture_review.dependency_guidance:
            dependency = max(dependency, 0.75)
        overall = (
            discovery.confidence.objective
            + discovery.confidence.repository
            + external_api
            + dependency
            + architecture
        ) / 5
        return DiscoveryConfidence(
            objective=discovery.confidence.objective,
            repository=discovery.confidence.repository,
            external_api=round(external_api, 2),
            dependency=round(dependency, 2),
            architecture=round(architecture, 2),
            overall=round(overall, 2),
            required=discovery.confidence.required,
        )

    def _planner_unlocked(
        self,
        discovery: DiscoveryResult,
        confidence: DiscoveryConfidence,
        research_results: list[ResearchResult],
        architecture_review: ArchitectureReview | None,
    ) -> bool:
        if any(blocker.resolver == "user" for blocker in discovery.blockers):
            return False
        if any(blocker.resolver == "research" for blocker in discovery.blockers) and not research_results:
            return False
        if any(blocker.resolver == "cloud_architect" for blocker in discovery.blockers):
            if architecture_review is None or not architecture_review.architecture_approved:
                return False
        return confidence.overall >= confidence.required

    def _build_lineage(self, discovery: DiscoveryResult) -> list[BlockerLineage]:
        return [
            BlockerLineage(
                blocker_id=f"DISC-{index:03d}",
                blocker_code=blocker.code,
                resolver=blocker.resolver,
            )
            for index, blocker in enumerate(discovery.blockers, start=1)
        ]

    def _resolve_lineage(self, lineage: list[BlockerLineage], *, resolver: str, resolved_by: str, evidence_ids: list[str]) -> None:
        for item in lineage:
            if item.resolver == resolver:
                item.resolved = True
                item.resolved_by = resolved_by
                item.evidence_ids = evidence_ids

    def _research_topics(self, objective: str, discovery: DiscoveryResult) -> list[str]:
        objective_l = objective.lower()
        if "jira" in objective_l:
            return ["Jira Cloud API authentication", "Jira issue creation endpoint", "Jira comment endpoint"]
        return [blocker.message for blocker in discovery.blockers if blocker.resolver == "research"]

    def _result(
        self,
        status: str,
        discovery: DiscoveryResult,
        research_results: list[ResearchResult],
        architecture_review: ArchitectureReview | None,
        confidence: DiscoveryConfidence,
        lineage: list[BlockerLineage],
    ) -> DiscoveryResolutionResult:
        return DiscoveryResolutionResult(
            status=status,  # type: ignore[arg-type]
            discovery=discovery,
            research_results=research_results,
            architecture_review=architecture_review,
            confidence=confidence,
            blocker_lineage=lineage,
        )

    def _persist(
        self,
        run_id: str,
        objective: str,
        discovery: DiscoveryResult,
        answers: dict[str, Any],
        result: DiscoveryResolutionResult,
    ) -> None:
        self.artifact_service.persist_artifacts(
            run_id=run_id,
            artifacts={
                "objective.json": {"objective": objective, "created_at": self.artifact_service.timestamp()},
                "discovery_packet.json": discovery,
                "user_answers.json": answers,
                "research_result.json": result.research_results,
                "architecture_review.json": result.architecture_review or {},
                "confidence_state.json": result.confidence,
                "blocker_lineage.json": result.blocker_lineage,
                "worker_profiles.json": self.profile_service.dump_profiles(["research_worker", "cloud_architect", "ux_architect"]),
            },
        )
