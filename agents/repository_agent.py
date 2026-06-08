from __future__ import annotations

from pathlib import Path
from typing import Any


REPO_ROOT = Path(".").resolve()

IGNORED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "artifacts",
}

TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
}


def _is_ignored(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    return any(part in IGNORED_PARTS for part in relative.parts)


def _list_files() -> list[str]:
    files: list[str] = []

    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if _is_ignored(path):
            continue

        files.append(str(path.relative_to(REPO_ROOT)))

    return sorted(files)


def _read_file(path_text: str, max_chars: int = 12000) -> dict[str, Any]:
    path = (REPO_ROOT / path_text).resolve()

    if not path.is_relative_to(REPO_ROOT):
        return {
            "path": path_text,
            "error": "Path escapes repository root.",
        }

    if not path.exists():
        return {
            "path": path_text,
            "error": "File does not exist.",
        }

    if path.suffix not in TEXT_EXTENSIONS:
        return {
            "path": path_text,
            "error": f"Unsupported file type: {path.suffix}",
        }

    text = path.read_text(encoding="utf-8", errors="replace")
    limited = text[:max_chars]

    return {
        "path": path_text,
        "content": limited,
        "lines": [
            {
                "line": index,
                "text": line,
            }
            for index, line in enumerate(limited.splitlines(), start=1)
        ],
        "truncated": len(text) > max_chars,
        "char_count": len(text),
    }

def _search_code(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    if not query.strip():
        return results

    for file_path in _list_files():
        path = REPO_ROOT / file_path

        if path.suffix not in TEXT_EXTENSIONS:
            continue

        text = path.read_text(encoding="utf-8", errors="replace")

        for line_number, line in enumerate(text.splitlines(), start=1):
            if query in line:
                results.append({
                    "path": file_path,
                    "line": line_number,
                    "text": line.strip(),
                })

                if len(results) >= max_results:
                    return results

    return results


def run(payload: dict[str, Any]) -> dict[str, Any]:
    work_order = payload.get("work_order")

    if work_order:
        instructions = "\n".join(
            work_order.get("instructions", [])
        )

        target_files = []
    else:
        instructions = payload.get(
            "instructions",
            "",
        )

        target_files = payload.get(
            "target_files",
            [],
        )

    files = _list_files()

    read_targets = []
    target_files = payload.get("target_files", [])

    file_reads = [
        _read_file(path)
        for path in target_files
    ]
    search_terms = []

    for file_path in files:
        if file_path in instructions:
            read_targets.append(file_path)

    if "get_messages" in instructions:
        search_terms.append("get_messages")

    if "collaboration" in instructions:
        search_terms.append("collaboration")

    if "registry" in instructions:
        search_terms.append("AGENT_REGISTRY")

    file_reads = [
        _read_file(path)
        for path in sorted(set(read_targets))
    ]

    searches = {
        term: _search_code(term)
        for term in sorted(set(search_terms))
    }

    return {
        "agent": "repository",
        "status": "completed",
        "summary": "RepositoryAgent inspected repository files and gathered read-only code evidence.",
        "files": files,
        "file_count": len(files),
        "read_files": file_reads,
        "searches": searches,
        "risks": [
            "Read-only inspection only. No files modified.",
        ],
        "questions": [
            "No questions or blockers.",
        ],
    }