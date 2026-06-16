from __future__ import annotations

from pathlib import Path
from typing import Any

from services.repository_evidence_service import RepositoryEvidenceService, TEXT_EXTENSIONS


REPO_ROOT = Path(".").resolve()


def _evidence_service() -> RepositoryEvidenceService:
    return RepositoryEvidenceService(REPO_ROOT)


def _is_ignored(path: Path) -> bool:
    relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    return _evidence_service().is_ignored_path(relative)


def _list_files() -> list[str]:
    return _evidence_service().list_source_files()


def _read_file(
    path_text: str,
    max_chars: int = 12000,
    requested_operation: str | None = None,
) -> dict[str, Any]:
    path = (REPO_ROOT / path_text).resolve()

    if not path.is_relative_to(REPO_ROOT):
        return {
            "path": path_text,
            "error": "Path escapes repository root.",
        }

    if not path.exists():
        if requested_operation == "create_file":
            return {
                "path": path_text,
                "exists": False,
                "requested_operation": "create_file",
                "target_file_missing": True,
                "file_missing_create_allowed": True,
                "repository_evidence_status": "missing_allowed_for_create",
                "summary": "Target file does not exist and is valid evidence for create_file.",
            }

        return {
            "path": path_text,
            "exists": False,
            "requested_operation": requested_operation or "replace_file",
            "target_file_missing": True,
            "file_missing_create_allowed": False,
            "repository_evidence_status": "missing_violation",
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
        "exists": True,
        "requested_operation": requested_operation,
        "target_file_missing": False,
        "file_missing_create_allowed": False,
        "repository_evidence_status": "available",
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

    read_targets = []
    target_files = payload.get("target_files", [])
    constraints = payload.get("constraints", {}) or {}
    requested_operation = payload.get("requested_operation")

    if requested_operation is None:
        allowed_operations = constraints.get("allowed_operations", [])
        if constraints.get("allow_create_files") or "create_file" in allowed_operations:
            requested_operation = "create_file"
        else:
            requested_operation = "replace_file"

    read_targets = sorted(set(read_targets + target_files))

    file_reads = [
        _read_file(path, requested_operation=requested_operation)
        for path in read_targets
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

    searches = {
        term: _search_code(term)
        for term in sorted(set(search_terms))
    }

    evidence_limit = int((constraints or {}).get("evidence_file_limit", 12) or 12)
    selected_files = _evidence_service().select_evidence_files(
        objective=payload.get("objective", "") or instructions,
        target_files=target_files,
        known_files=files,
        limit=evidence_limit,
    )

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
        "requested_operation": requested_operation,
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