import os
import requests
from dotenv import load_dotenv


load_dotenv()


def check_ollama(config: dict) -> dict:
    try:
        base_url = config["providers"]["ollama"]["base_url"]
        response = requests.get(f"{base_url}/api/tags", timeout=5)

        return {
            "status": "online" if response.ok else "error",
            "status_code": response.status_code
        }

    except Exception as e:
        return {
            "status": "offline",
            "error": str(e)
        }


def check_openrouter(config: dict) -> dict:
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            return {
                "status": "offline",
                "error": "OPENROUTER_API_KEY is not set"
            }

        base_url = config["providers"]["openrouter"]["base_url"]

        response = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )

        return {
            "status": "online" if response.ok else "error",
            "status_code": response.status_code
        }

    except Exception as e:
        return {
            "status": "offline",
            "error": str(e)
        }


def get_health(config: dict) -> dict:
    providers = {
        "ollama": check_ollama(config),
        "openrouter": check_openrouter(config)
    }

    overall = "healthy"

    for provider in providers.values():
        if provider["status"] != "online":
            overall = "degraded"

    return {
        "status": overall,
        "providers": providers
    }