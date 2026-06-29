import time
import yaml
from logger import log_request
from providers.ollama import generate as ollama_generate
from providers.openrouter import generate as openrouter_generate
from llm.router import deterministic_scan


with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


PROVIDERS = {
    "ollama": ollama_generate,
    "openrouter": openrouter_generate,
}

PURPOSE_MODEL_MAP = {
    "planning": "local_reasoning",
    "dev_worker_proposal": "local_coding",
    "code_proposal": "local_coding",
    "code_review": "local_coding",
    "conversation_context_evaluation": "local_reasoning",
}


def choose_model(config: dict, prompt: str, purpose: str | None = None):
    signals = deterministic_scan(prompt)
    models = config["models"]

    if purpose in PURPOSE_MODEL_MAP:
        model_key = PURPOSE_MODEL_MAP[purpose]
        if model_key in models:
            model_cfg = models[model_key]
            return (
                model_key,
                model_cfg["provider"],
                f"Router selected purpose route for {purpose}",
            )

    if signals.sensitive_data and "local_fast" in models:
        model_key = "local_fast"
        model_cfg = models[model_key]
        return model_key, model_cfg["provider"], "Router kept sensitive request local"

    if signals.needs_current_info and "cloud_fast" in models:
        model_key = "cloud_fast"
        model_cfg = models[model_key]
        return model_key, model_cfg["provider"], "Router selected cloud route for current/external info"

    if signals.needs_code and "local_coding" in models:
        model_key = "local_coding"
        model_cfg = models[model_key]
        return model_key, model_cfg["provider"], "Router selected local coding route"

    if signals.needs_large_context and "cloud_reasoning" in models:
        model_key = "cloud_reasoning"
        model_cfg = models[model_key]
        return model_key, model_cfg["provider"], "Router selected cloud reasoning route for large context"

    if signals.needs_precision and "cloud_reasoning" in models:
        model_key = "cloud_reasoning"
        model_cfg = models[model_key]
        return model_key, model_cfg["provider"], "Router selected cloud reasoning route for precision-sensitive request"

    if not signals.simple_chat and "local_reasoning" in models:
        model_key = "local_reasoning"
        model_cfg = models[model_key]
        return model_key, model_cfg["provider"], "Router selected local reasoning route"

    model_key = config.get("routing", {}).get("local_model", "local_fast")
    model_cfg = models[model_key]
    return model_key, model_cfg["provider"], "Default local route"


def route_prompt(prompt: str, purpose: str | None = None):
    start = time.time()

    model_key, provider_name, reason = choose_model(
        config=config,
        prompt=prompt,
        purpose=purpose,
    )

    model_cfg = config["models"][model_key]
    provider_generate = PROVIDERS[provider_name]
    fallback_used = False

    try:
        response = provider_generate(prompt, config, model_cfg)

    except Exception as ex:
        print(f"[Router] Primary route failed: {ex}")

        if provider_name != "openrouter":
            fallback_key = "cloud_fast"
            fallback_cfg = config["models"][fallback_key]

            response = openrouter_generate(
                prompt,
                config,
                fallback_cfg,
            )

            provider_name = "openrouter"
            model_key = fallback_key
            model_cfg = fallback_cfg
            fallback_used = True
            reason = (
                f"{reason} | Fallback to cloud after failure"
            )

        else:
            raise

    elapsed_ms = int((time.time() - start) * 1000)

    log_request({
        "route": provider_name,
        "reason": reason,
        "model_key": model_key,
        "model": model_cfg["model"],
        "provider": provider_name,
        "elapsed_ms": elapsed_ms,
        "prompt_length": len(prompt),
        "response_length": len(response),
        "fallback_used": fallback_used,
    })

    return {
        "route": provider_name,
        "reason": reason,
        "model_key": model_key,
        "model": model_cfg["model"],
        "elapsed_ms": elapsed_ms,
        "response": response,
        "fallback_used": fallback_used,
    }
