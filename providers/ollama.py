import os
import requests


def generate(prompt: str, config: dict, model_cfg: dict) -> str:
    ollama_cfg = config["providers"]["ollama"]
    base_url = os.environ.get("OLLAMA_BASE_URL") or ollama_cfg["base_url"]

    url = f"{base_url}/api/generate"

    payload = {
        "model": model_cfg["model"],
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, json=payload, timeout=120)

    if not response.ok:
        raise Exception(f"Ollama error {response.status_code}: {response.text}")

    data = response.json()
    return data.get("response", "")