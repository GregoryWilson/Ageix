from __future__ import annotations

from typing import Any, Protocol

from models.interactive_prompt import InteractivePrompt


class PromptRenderer(Protocol):
    """UI-neutral prompt rendering contract for CLI, web, or chat clients."""

    def render(self, prompt: InteractivePrompt) -> str:
        ...


class CliPromptRenderer:
    """First adapter for interactive consultations.

    This renderer intentionally returns text instead of calling input(); orchestration
    can pause and expose the rendered prompt to CLI or future web clients.
    """

    def render(self, prompt: InteractivePrompt) -> str:
        lines = [
            f"Consultation Session: {prompt.consultation_id}",
            f"Turn: {prompt.turn_number}",
            f"Participant: {prompt.participant_id}",
            "",
            prompt.title,
        ]
        if prompt.objective:
            lines.extend(["", "Objective:", prompt.objective])
        lines.extend(["", prompt.prompt_text])
        if prompt.available_evidence:
            lines.extend(["", "Available Evidence:"])
            for item in prompt.available_evidence:
                evidence_id = item.get("evidence_id", "")
                evidence_type = item.get("evidence_type") or item.get("type", "unknown")
                summary = item.get("summary", "")
                requestable = "requestable" if item.get("requestable", True) else "not requestable"
                lines.append(f"- {evidence_id} [{evidence_type}, {requestable}]: {summary}")
        lines.extend([
            "",
            "Required Response Fields:",
            "- recommendation",
            "- confidence (0.0 - 1.0)",
            "- evidence_sufficient (true/false)",
            "- requested_followup_evidence EV-* IDs only, if needed",
        ])
        return "\n".join(lines)


def build_available_evidence(evidence_dictionary: dict[str, Any]) -> list[dict[str, Any]]:
    """Return UI-safe evidence metadata without raw payloads."""

    items = evidence_dictionary.get("items", []) if evidence_dictionary else []
    safe_items: list[dict[str, Any]] = []
    for item in items:
        safe_items.append({
            "evidence_id": item.get("evidence_id"),
            "evidence_type": item.get("evidence_type") or item.get("type"),
            "summary": item.get("summary", ""),
            "estimated_tokens": item.get("estimated_tokens", 0),
            "requestable": item.get("requestable", True),
        })
    return safe_items
