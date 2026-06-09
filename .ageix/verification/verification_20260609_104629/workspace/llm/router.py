import json
import re
from llm.schemas import RouteSignals, RouteDecision

CURRENT_INFO_TERMS = [
    "latest", "current", "today", "yesterday", "tomorrow",
    "news", "price", "stock", "weather", "recent",
    "schedule", "version", "release", "available now"
]

PRECISION_TERMS = [
    "legal", "medical", "tax", "financial advice",
    "lawsuit", "diagnosis", "prescription", "compliance"
]

CODE_TERMS = [
    "python", "javascript", "typescript", "java", "sql",
    "bml", "api", "function", "class", "bug", "stack trace",
    "fastapi", "pydantic", "docker", "git", "code"
]

SENSITIVE_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"(?i)api[_\- ]?key\s*[:=]\s*[A-Za-z0-9_\-]{12,}",
    r"(?i)password\s*[:=]",
    r"\b(?:\d[ -]*?){13,16}\b",
]


LOCAL_CONTEXT_LIMIT = 8192


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def detect_sensitive_data(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in SENSITIVE_PATTERNS)


def deterministic_scan(prompt: str, context: str = "") -> RouteSignals:
    combined = f"{prompt}\n{context}".strip()
    token_estimate = estimate_tokens(combined)

    return RouteSignals(
        needs_current_info=contains_any(prompt, CURRENT_INFO_TERMS),
        needs_large_context=token_estimate > int(LOCAL_CONTEXT_LIMIT * 0.75),
        needs_precision=contains_any(prompt, PRECISION_TERMS),
        needs_code=contains_any(prompt, CODE_TERMS),
        simple_chat=token_estimate < 300 and not contains_any(prompt, CURRENT_INFO_TERMS + PRECISION_TERMS + CODE_TERMS),
        sensitive_data=detect_sensitive_data(combined),
        token_estimate=token_estimate,
    )


def rule_based_decision(signals: RouteSignals) -> RouteDecision | None:
    if signals.needs_current_info:
        return RouteDecision(
            route="web_research",
            confidence=0.95,
            reason="Request appears to require current or external information.",
            requires_web=True,
            expected_difficulty="medium",
            fallback_route="cloud_balanced",
        )

    if signals.sensitive_data:
        return RouteDecision(
            route="local_fast",
            confidence=0.9,
            reason="Sensitive data detected; keeping request local.",
            expected_difficulty="medium",
            fallback_route="local_fast",
        )

    if signals.needs_large_context:
        return RouteDecision(
            route="cloud_balanced",
            confidence=0.85,
            reason="Request context is too large for the preferred local context window.",
            expected_difficulty="hard",
            fallback_route="cloud_deep",
        )

    if signals.simple_chat:
        return RouteDecision(
            route="local_fast",
            confidence=0.9,
            reason="Simple request suitable for local response.",
            expected_difficulty="simple",
            fallback_route="cloud_balanced",
        )

    return None


def validate_decision(decision: RouteDecision, signals: RouteSignals) -> RouteDecision:
    if signals.needs_current_info and decision.route != "web_research":
        decision.route = "web_research"
        decision.requires_web = True
        decision.reason = "Overridden because current information appears required."

    if signals.sensitive_data and decision.route.startswith("cloud"):
        decision.route = "local_fast"
        decision.reason = "Overridden because sensitive data was detected."

    if decision.confidence < 0.5:
        decision.route = "cloud_balanced"
        decision.reason = "Router confidence was too low; using safer balanced cloud route."

    return decision


def build_router_prompt(prompt: str, context: str, signals: RouteSignals) -> str:
    return f"""
You are the Ageix routing engine.

Choose the best execution route for the user's request.

Available routes:
- local_fast: local Ollama model, fast, private, weaker reasoning
- local_coder: local coding model, better for programming
- cloud_balanced: stronger cloud model, balanced cost/reasoning
- cloud_deep: strongest cloud model, expensive and slower
- web_research: requires current or external information

Deterministic signals:
{signals.model_dump_json(indent=2)}

User prompt:
{prompt}

Relevant context:
{context[:6000]}

Return only valid JSON:
{{
  "route": "local_fast|local_coder|cloud_balanced|cloud_deep|web_research",
  "confidence": 0.0,
  "reason": "short explanation",
  "requires_rag": false,
  "requires_web": false,
  "expected_difficulty": "simple|medium|hard",
  "fallback_route": "local_fast|local_coder|cloud_balanced|cloud_deep|web_research"
}}
""".strip()


async def decide(prompt: str, context: str = "", router_llm=None) -> RouteDecision:
    signals = deterministic_scan(prompt, context)

    forced = rule_based_decision(signals)
    if forced:
        return forced

    if router_llm is None:
        if signals.needs_code:
            return RouteDecision(
                route="local_coding",
                confidence=0.75,
                reason="Code-related request detected; no router LLM configured.",
                expected_difficulty="medium",
                fallback_route="cloud_balanced",
            )

        return RouteDecision(
            route="cloud_balanced",
            confidence=0.65,
            reason="No router LLM configured; using balanced fallback.",
            expected_difficulty="medium",
            fallback_route="cloud_deep",
        )

    router_prompt = build_router_prompt(prompt, context, signals)
    raw = await router_llm(router_prompt)

    try:
        data = json.loads(raw)
        decision = RouteDecision(**data)
    except Exception:
        decision = RouteDecision(
            route="cloud_balanced",
            confidence=0.5,
            reason="Router LLM returned invalid JSON; using fallback.",
            expected_difficulty="medium",
            fallback_route="cloud_deep",
        )

    return validate_decision(decision, signals)