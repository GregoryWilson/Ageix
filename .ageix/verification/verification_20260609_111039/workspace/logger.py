import json
import time
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "ageix.log"


def log_request(entry: dict):
    LOG_DIR.mkdir(exist_ok=True)

    entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")