from typing import Any

from router import route_prompt


def invoke_llm(
    purpose: str,
    prompt: str,
    context: dict[str, Any] | None = None,
    model_profile: str | None = None,
) -> dict[str, Any]:
    """
    Central gateway for all model interactions.
    """

    try:
        result = route_prompt(
            prompt=prompt,
            purpose=purpose,
        )

        return {
            "purpose": purpose,
            "status": "completed",
            **result,
        }

    except Exception as ex:
        return {
            "purpose": purpose,
            "status": "failed",
            "response": "",
            "error": str(ex),
            "route": None,
            "model_key": None,
            "model": None,
            "reason": "LLM invocation failed",
            "elapsed_ms": None,
        }