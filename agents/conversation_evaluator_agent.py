import json
from typing import Any

from services.llm_service import invoke_llm


def build_conversation_evaluation_prompt(turns: list[dict]) -> str:
    return f"""
    You are the Ageix Chair, evaluating a shared multi-agent conversation.

    Conversation turns (oldest to newest):
    {json.dumps(turns, indent=2)}

    Assess the conversation and respond ONLY with a JSON object containing:
    - "conversation_summary": a brief running summary of the discussion
    - "deadlock_confidence": a number from 0.0 to 1.0, how confident you are
      that the participants are deadlocked (unable to converge without help)
    - "disagreement_summary": a brief summary of the disagreement, only
      relevant when deadlock_confidence is high; empty string otherwise
    - "confidence": your own self-assessed confidence (0.0 to 10.0) in this
      evaluation

    Respond with JSON only, no other text.
    """.strip()


def extract_json(raw: str) -> dict:
    cleaned = raw.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```", 1)[0].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```", 1)[0].strip()

    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(cleaned)
    return value


def run(payload: dict[str, Any]) -> dict[str, Any]:
    turns = payload.get("turns", [])

    prompt = build_conversation_evaluation_prompt(turns)

    result = invoke_llm(
        purpose="conversation_context_evaluation",
        prompt=prompt,
    )

    raw = result.get("response", "")

    try:
        data = extract_json(raw)
    except Exception:
        data = {}

    return {
        "agent": "conversation_evaluator",
        "conversation_summary": data.get("conversation_summary", ""),
        "deadlock_confidence": float(data.get("deadlock_confidence", 0.0) or 0.0),
        "disagreement_summary": data.get("disagreement_summary", ""),
        "confidence": float(data.get("confidence", 0.0) or 0.0),
        "raw_response": raw,
        "route": result.get("route"),
        "model_key": result.get("model_key"),
        "model": result.get("model"),
    }
