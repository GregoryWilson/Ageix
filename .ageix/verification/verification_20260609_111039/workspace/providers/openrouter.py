import os
import requests
from dotenv import load_dotenv


load_dotenv()


def generate(prompt: str, config: dict, model_cfg: dict) -> str:
    openrouter_cfg = config["providers"]["openrouter"]

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise Exception("OPENROUTER_API_KEY is not set in .env")

    url = f"{openrouter_cfg['base_url']}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": openrouter_cfg.get("referer", "http://localhost:8000"),
        "X-OpenRouter-Title": openrouter_cfg.get("app_title", "Ageix Gateway"),
    }

    payload = {
        "model": model_cfg["model"],
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    response = requests.post(url, headers=headers, json=payload, timeout=300)

    if not response.ok:
        raise Exception(f"OpenRouter error {response.status_code}: {response.text}")

    data = response.json()

    return data["choices"][0]["message"]["content"]
