from __future__ import annotations

from pathlib import Path
from typing import Any

from models.participant_response import ParticipantResponse
from services.consultation_orchestration_service import ConsultationOrchestrationService
from services.consultation_prompt_service import CliPromptRenderer
from services.consultation_session_service import ConsultationSessionService


class ConsultationApiService:
    """UI-facing service boundary for CLI, Open WebUI, and future REST endpoints."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.sessions = ConsultationSessionService(self.repo_root)
        self.orchestrator = ConsultationOrchestrationService(self.repo_root)
        self.renderer = CliPromptRenderer()

    def get_session(self, consultation_id: str) -> dict[str, Any]:
        return self.sessions.load_session(consultation_id)

    def get_pending_prompt(self, consultation_id: str, participant_id: str = "human_interactive") -> dict[str, Any]:
        prompt = self.orchestrator.start_interactive_turn(consultation_id, participant_id)
        return {
            "prompt": prompt.model_dump(),
            "rendered_text": self.renderer.render(prompt),
        }

    def submit_response(self, consultation_id: str, response: ParticipantResponse | dict[str, Any]) -> dict[str, Any]:
        parsed = response if isinstance(response, ParticipantResponse) else ParticipantResponse(**response)
        return self.orchestrator.submit_participant_response(consultation_id, parsed)

    def run_stub(self, consultation_id: str, participant_id: str = "stub_architect") -> dict[str, Any]:
        return self.orchestrator.run_stub_participant(consultation_id, participant_id)
