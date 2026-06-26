from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.discovery import (
    ArchitectureReviewSignal,
    DiscoveryAnswerValidation,
    DiscoveryBlocker,
    DiscoveryConfidence,
    DiscoveryQuestion,
    DiscoveryResult,
)


class DiscoveryService:
    """Deterministic readiness gate before planning/implementation.

    This is intentionally lightweight. It does not perform research or cloud review yet;
    it identifies when those inputs are required so 10.1 can plug in execution.
    """

    REQUIRED_CONFIDENCE = 0.75

    def analyze(
        self,
        *,
        objective: str,
        target_files: list[str] | None = None,
        answers: dict[str, Any] | None = None,
        allow_assumptions: bool = False,
    ) -> DiscoveryResult:
        answers = answers or {}
        objective_l = objective.lower()
        target_files = target_files or []
        is_external = self._mentions_external_integration(objective_l)
        is_jira = "jira" in objective_l
        is_new_worker = any(term in objective_l for term in ["new worker", "worker agent", "new agent", "agent"])

        questions = self._build_questions(is_jira=is_jira, is_external=is_external)
        answer_validation = [self._validate_answer(question, answers) for question in questions]

        blockers: list[DiscoveryBlocker] = []
        for question, validation in zip(questions, answer_validation):
            if not question.required:
                continue
            if validation.status in {"accepted", "accepted_uncertain"}:
                continue
            blockers.append(
                DiscoveryBlocker(
                    code=f"{question.id}_unresolved",
                    message=validation.message,
                    resolver=question.resolver,
                    question_id=question.id,
                )
            )

        if is_external and not self._has_research_evidence(answers):
            blockers.append(
                DiscoveryBlocker(
                    code="external_api_research_required",
                    message="External API usage requires documentation or research evidence before implementation.",
                    resolver="research",
                )
            )

        architecture = self._architecture_signal(
            objective_l=objective_l,
            is_external=is_external,
            is_new_worker=is_new_worker,
            answers=answers,
        )
        if architecture.review_required:
            blockers.append(
                DiscoveryBlocker(
                    code="architecture_review_required",
                    message="Architecture confidence is below the review threshold for this kind of change.",
                    resolver="cloud_architect",
                )
            )

        confidence = self._score_confidence(
            objective=objective,
            target_files=target_files,
            is_external=is_external,
            is_new_worker=is_new_worker,
            answer_validation=answer_validation,
            architecture=architecture,
            has_research_evidence=self._has_research_evidence(answers),
        )

        blocking = bool(blockers) or confidence.overall < confidence.required
        if allow_assumptions:
            # Assumptions can bypass user clarification, but not explicit architecture review.
            blocking = any(blocker.resolver in {"research", "cloud_architect", "human_reviewer"} for blocker in blockers)

        return DiscoveryResult(
            status="discovery_required" if blocking else "ready_for_planning",
            confidence=confidence,
            blockers=blockers,
            questions=questions,
            answer_validation=answer_validation,
            architecture=architecture,
            research_required=any(blocker.resolver == "research" for blocker in blockers),
            next_action=self._next_action(blockers),
        )

    def load_answers(self, path: str | Path | None) -> dict[str, Any]:
        if not path:
            return {}
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Discovery answer file must contain a JSON object.")
        return data

    def _build_questions(self, *, is_jira: bool, is_external: bool) -> list[DiscoveryQuestion]:
        if not is_external:
            return []

        questions = [
            DiscoveryQuestion(
                id="integration_use_case",
                question="What is the first useful capability this worker should provide?",
                allowed_values=["read_only", "create", "update", "search", "create_and_comment", "unknown"],
                guidance="Pick the smallest useful first increment. For Jira, create_issue plus add_comment is a reasonable first write-capable scaffold.",
            ),
            DiscoveryQuestion(
                id="dependency_policy",
                question="What dependency policy should this implementation follow?",
                allowed_values=["stdlib_only", "allow_existing_manifest_only", "allow_new_dependencies_with_manifest_update", "ask_before_new_dependency", "unknown"],
                guidance="For a safe first pass, use stdlib_only or existing manifest dependencies and mock all network calls.",
            ),
            DiscoveryQuestion(
                id="config_location",
                question="Where should credentials and endpoint configuration live?",
                allowed_values=["environment_variables", "controls_json", "project_config", "existing_repo_pattern", "unknown"],
                guidance="Environment variables are usually safest for credentials. controls.json can govern policy, not secret values.",
            ),
        ]

        if is_jira:
            questions.insert(
                0,
                DiscoveryQuestion(
                    id="jira_platform",
                    question="Which Jira platform is the target?",
                    allowed_values=["jira_cloud", "jira_data_center", "existing_repo_pattern", "unknown"],
                    guidance="Jira Cloud commonly uses email plus API token for simple scripts. Jira Data Center often supports Personal Access Tokens.",
                ),
            )
            questions.insert(
                1,
                DiscoveryQuestion(
                    id="jira_auth_method",
                    question="How should Jira authenticate?",
                    allowed_values=["api_token", "oauth2", "personal_access_token", "existing_repo_pattern", "unknown"],
                    guidance="For Jira Cloud, common options are API token with email/basic auth, OAuth 2.0, or Atlassian app auth. For Jira Data Center, common options include Personal Access Token, basic auth if enabled, or OAuth depending on server configuration.",
                ),
            )

        return questions

    def _validate_answer(self, question: DiscoveryQuestion, answers: dict[str, Any]) -> DiscoveryAnswerValidation:
        if question.id not in answers:
            return DiscoveryAnswerValidation(
                question_id=question.id,
                status="missing",
                message=f"Required discovery answer is missing: {question.id}.",
                guidance=question.guidance,
            )

        received = answers.get(question.id)
        if isinstance(received, str) and self._is_guidance_request(received):
            return DiscoveryAnswerValidation(
                question_id=question.id,
                status="guidance_requested",
                received=received,
                message=f"Guidance requested for {question.id}.",
                guidance=question.guidance,
            )

        values = received if isinstance(received, list) else [received]
        normalized = [str(value).strip().lower().replace("-", "_").replace(" ", "_") for value in values]

        if "unknown" in normalized or "not_sure" in normalized:
            return DiscoveryAnswerValidation(
                question_id=question.id,
                status="accepted_uncertain",
                received=received,
                normalized_value="unknown",
                message=f"Answer accepted as uncertain for {question.id}; confidence was not raised.",
                guidance=question.guidance,
                confidence_delta=0.0,
            )

        allowed = set(question.allowed_values)
        invalid = [value for value in normalized if value not in allowed]
        if invalid:
            return DiscoveryAnswerValidation(
                question_id=question.id,
                status="invalid",
                received=received,
                message=f"Unsupported answer for {question.id}: {', '.join(invalid)}.",
                guidance=question.guidance,
            )

        normalized_value: Any = normalized if isinstance(received, list) else normalized[0]
        return DiscoveryAnswerValidation(
            question_id=question.id,
            status="accepted",
            received=received,
            normalized_value=normalized_value,
            message=f"Answer accepted for {question.id}.",
            confidence_delta=0.10,
        )

    def _score_confidence(
        self,
        *,
        objective: str,
        target_files: list[str],
        is_external: bool,
        is_new_worker: bool,
        answer_validation: list[DiscoveryAnswerValidation],
        architecture: ArchitectureReviewSignal,
        has_research_evidence: bool,
    ) -> DiscoveryConfidence:
        objective_score = 0.45
        if len(objective.strip()) >= 60:
            objective_score += 0.15
        if target_files:
            objective_score += 0.10
        accepted = sum(1 for item in answer_validation if item.status == "accepted")
        total = len(answer_validation) or 1
        objective_score += min(0.20, accepted * 0.05)
        objective_score = min(objective_score, 0.95)

        repository_score = 0.80 if target_files else 0.60
        dependency_score = 0.45 if is_external else 0.80
        if any(item.question_id == "dependency_policy" and item.status == "accepted" for item in answer_validation):
            dependency_score = 0.75

        external_api_score = 0.90 if not is_external else 0.35
        if has_research_evidence:
            external_api_score = 0.80

        overall = min(
            objective_score,
            repository_score,
            dependency_score,
            external_api_score,
            architecture.confidence,
        )

        return DiscoveryConfidence(
            objective=round(objective_score, 2),
            repository=round(repository_score, 2),
            external_api=round(external_api_score, 2),
            dependency=round(dependency_score, 2),
            architecture=round(architecture.confidence, 2),
            overall=round(overall, 2),
            required=self.REQUIRED_CONFIDENCE,
        )

    def _architecture_signal(
        self,
        *,
        objective_l: str,
        is_external: bool,
        is_new_worker: bool,
        answers: dict[str, Any],
    ) -> ArchitectureReviewSignal:
        reasons: list[str] = []
        confidence = 0.85

        if is_new_worker:
            confidence -= 0.20
            reasons.append("New worker or agent type")
        if is_external:
            confidence -= 0.20
            reasons.append("New external integration")
        if any(term in objective_l for term in ["auth", "authenticate", "credential", "api token", "oauth"]):
            confidence -= 0.10
            reasons.append("Authentication or credential strategy involved")
        if "architecture_review" in answers and str(answers["architecture_review"]).lower() in {"complete", "approved"}:
            confidence = max(confidence, 0.85)
            reasons = [reason for reason in reasons if reason]

        confidence = max(0.0, round(confidence, 2))
        review_recommended = confidence < 0.85 or bool(reasons)
        review_required = confidence < 0.75 and not str(answers.get("architecture_review", "")).lower() in {"complete", "approved"}
        return ArchitectureReviewSignal(
            confidence=confidence,
            review_recommended=review_recommended,
            review_required=review_required,
            preferred_reviewer="cloud_architect" if review_recommended else "none",
            reasons=reasons,
        )

    def _mentions_external_integration(self, objective_l: str) -> bool:
        terms = ["api", "sdk", "library", "jira", "octoprint", "octopi", "salesforce", "github", "external", "connects"]
        return any(term in objective_l for term in terms)

    def _has_research_evidence(self, answers: dict[str, Any]) -> bool:
        return bool(answers.get("research_evidence") or answers.get("external_api_evidence"))

    def _is_guidance_request(self, value: str) -> bool:
        lowered = value.lower()
        return "option" in lowered or "what are" in lowered or "help" in lowered or "guidance" in lowered

    def _next_action(self, blockers: list[DiscoveryBlocker]) -> str:
        if not blockers:
            return "Proceed to planning."
        if any(blocker.resolver == "cloud_architect" for blocker in blockers):
            return "Resolve architecture review before implementation."
        if any(blocker.resolver == "research" for blocker in blockers):
            return "Provide research evidence or route to a research worker."
        return "Provide structured discovery answers."
