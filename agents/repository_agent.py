from __future__ import annotations

from pathlib import Path
from typing import Any

from services.repository_evidence_service import RepositoryEvidenceService


REPO_ROOT = Path(".").resolve()

IGNORED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "venv",
    ".venv",
    "artifacts",
}

AGEIX_RUNTIME_DIRS = {
    "logs",
    "manifests",
    "staged",
    "staging",
    "runs",
    "verification",
    "runtime",
    "repair_loops",
    "user_feedback",
}

AGEIX_SOURCE_DIRS = {
    "config",
    "projects",
    "objectives",
    "architecture",
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
    parts = relative.parts
    if any(part in IGNORED_PARTS for part in parts):
        return True
    if len(parts) >= 2 and parts[0] == ".ageix":
        if parts[1] in AGEIX_RUNTIME_DIRS:
            return True
        if parts[1] not in AGEIX_SOURCE_DIRS:
            return True
    return False


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
            "target_file_missing": True,
            "file_missing_create_allowed": False,
            "repository_evidence_status": "missing_violation",
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
        "content_mode": "partial_file" if len(text) > max_chars else "full_file",
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

    evidence_limit = payload.get("constraints", {}).get("evidence_file_limit", 12)
    try:
        evidence_limit = int(evidence_limit)
    except (TypeError, ValueError):
        evidence_limit = 12

    selected_files = RepositoryEvidenceService(REPO_ROOT).select_evidence_files(
        objective=payload.get("objective", instructions),
        target_files=payload.get("target_files", []),
        known_files=files,
        limit=evidence_limit,
    )

    read_targets = []
    target_files = payload.get("target_files", [])

    read_targets = sorted(set(read_targets + target_files))

    requested_operation = payload.get("requested_operation")
    allow_create_files = requested_operation == "create_file" or payload.get("allow_create_files") is True

    file_reads = []
    for path in read_targets:
        read = _read_file(path)
        if read.get("target_file_missing") is True and allow_create_files:
            read["file_missing_create_allowed"] = True
            read["repository_evidence_status"] = "missing_allowed_for_create"
        file_reads.append(read)

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
        "selected_files": selected_files,
        "selected_file_count": len(selected_files),
        "read_files": file_reads,
        "evidence": file_reads,
        "searches": searches,
        "risks": [
            "Read-only inspection only. No files modified.",
        ],
        "questions": [
            "No questions or blockers.",
        ],
    }

def _read_project_file_for_repair(self, file_path: str) -> dict[str, Any]:
    path = self.repo_root / file_path

    if not path.exists():
        return {
            "path": file_path,
            "exists": False,
            "content": "",
            "reason": "file_not_found",
        }

    if not path.is_file():
        return {
            "path": file_path,
            "exists": False,
            "content": "",
            "reason": "not_a_file",
        }

    return {
        "path": file_path,
        "exists": True,
        "content": path.read_text(encoding="utf-8"),
    }


def collect_repair_evidence(repair_work_order: dict[str, Any]) -> dict[str, Any]:
    patch_id = str(repair_work_order.get("patch_id", ""))
    source_verification_id = str(repair_work_order.get("source_verification_id", ""))
    attempt_number = int(repair_work_order.get("attempt_number", 1))
    failure_reason = str(repair_work_order.get("failure_reason", ""))

    objective = repair_work_order.get("objective")
    repair_objective = repair_work_order.get("repair_objective")

    files: list[dict[str, Any]] = []
    dependency_hints: list[str] = []
    supporting_evidence: list[str] = [
        f"Patch ID: {patch_id}",
        f"Source verification ID: {source_verification_id}",
        f"Repair attempt: {attempt_number}",
    ]

    if objective:
        supporting_evidence.append(f"Original objective: {objective}")

    if repair_objective:
        supporting_evidence.append(f"Repair objective: {repair_objective}")

    if failure_reason:
        supporting_evidence.append(f"Failure reason: {failure_reason}")

    changed_files = repair_work_order.get("changed_files")
    if isinstance(changed_files, list):
        for file_path in changed_files:
            if isinstance(file_path, str):
                files.append(_read_file(file_path))

    return {
        "evidence_type": "repair_repository_evidence",
        "patch_id": patch_id,
        "source_verification_id": source_verification_id,
        "attempt_number": attempt_number,
        "failure_reason": failure_reason,
        "objective": objective,
        "repair_objective": repair_objective,
        "files": files,
        "dependency_hints": dependency_hints,
        "supporting_evidence": supporting_evidence,
    }