from __future__ import annotations

import json
from typing import Any

from services.llm_service import invoke_llm
from utils.prompt_loader import load_prompt
from models.patch_proposal import PatchProposal, ContextRequest
from services.patch_proposal_contract_service import PatchProposalContractService

SYSTEM_PROMPT = load_prompt("dev_worker_system.txt")


def build_devworker_prompt(packet: dict[str, Any]) -> str:
    return f"""
{SYSTEM_PROMPT}

Runtime Packet:
{json.dumps(packet, indent=2)}

Return only valid JSON.
""".strip()


def extract_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    return json.loads(cleaned)


def normalize_devworker_result(
    data: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    if data.get("response_type") and not data.get("result_type"):
        data["result_type"] = data.pop("response_type")

    data.setdefault("agent", "devworker")
    data.setdefault("mode", "proposal_only")
    data.setdefault("objective", packet.get("objective", ""))
    data.setdefault(
        "summary",
        f"Patch proposal for {packet.get('objective', 'requested work')}"
    )

    data["notes"] = ensure_list(data.get("notes"))
    data["test_plan"] = ensure_list(data.get("test_plan"))

    repo_evidence = ensure_list(packet.get("repo_evidence"))
    dependency_hints = ensure_list(packet.get("dependency_hints"))
    target_files = ensure_list(packet.get("target_files"))

    data["files_considered"] = ensure_list(
        data.get("files_considered") or target_files
    )

    data["evidence_used"] = ensure_list(
        data.get("evidence_used") or repo_evidence
    )

    data["dependency_hints_used"] = ensure_list(
        data.get("dependency_hints_used") or dependency_hints
    )

    data["assumptions"] = ensure_list(data.get("assumptions"))
    data["dependency_risks"] = ensure_list(data.get("dependency_risks"))
    data["changes"] = ensure_list(data.get("changes"))
    data["proposed_changes"] = ensure_list(data.get("proposed_changes"))
    data["test_plan"] = ensure_list(data.get("test_plan"))
    data["no_write_confirmation"] = True

    normalized, _evidence = PatchProposalContractService().normalize(data, source_agent="devworker")
    return normalized


def build_fallback_result(
    *,
    packet: dict[str, Any],
    raw: str,
    error: str,
) -> dict[str, Any]:
    return {
        "agent": "devworker",
        "mode": "proposal_only",
        "objective": packet.get("objective", ""),
        "files_considered": [],
        "evidence_used": [],
        "dependency_hints_used": packet.get("dependency_hints", []),
        "assumptions": [
            "DevWorker LLM output could not be parsed as valid JSON."
        ],
        "dependency_risks": [
            error
        ],
        "proposed_changes": [],
        "test_plan": [],
        "no_write_confirmation": True,
        "raw_response": raw,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = normalize_devworker_packet(payload)
    prompt = build_devworker_prompt(normalized_payload)

    print("[DevWorker] Invoking LLM...", flush=True)

    llm_result = invoke_llm(
        purpose="dev_worker_proposal",
        prompt=prompt,
    )

    print("[DevWorker] LLM returned.", flush=True)

    raw = llm_result.get("response", "")

    try:
        deliverable = extract_json(raw)
        deliverable = normalize_devworker_result(deliverable, normalized_payload)
        validation_error = None
    except Exception as ex:
        validation_error = str(ex)
        deliverable = build_fallback_result(
            packet=normalized_payload,
            raw=raw,
            error=validation_error,
        )

    return {
        "status": "completed" if validation_error is None else "blocked",
        "summary": (
            "DevWorker generated an evidence-aware proposal."
            if validation_error is None
            else "DevWorker failed to generate valid proposal JSON."
        ),
        "changed_files": [],
        "commands_run": [],
        "errors": [] if validation_error is None else [validation_error],
        "questions": [],
        "next_recommendation": "Review the proposal before allowing any execution.",
        "deliverable": deliverable,
        "route": llm_result.get("route"),
        "model_key": llm_result.get("model_key"),
        "model": llm_result.get("model"),
        "reason": llm_result.get("reason"),
        "elapsed_ms": llm_result.get("elapsed_ms"),
    }

def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_devworker_result(raw: str):
    try:
        data = json.loads(raw)

        result_type = data.get("result_type")

        if result_type == "patch_proposal":
            return PatchProposal.model_validate(data)

        if result_type == "context_request":
            return ContextRequest.model_validate(data)

    except Exception:
        pass

    return {
        "result_type": "prose",
        "content": raw,
    }


def get_work_type(packet: dict[str, Any]) -> str:
    return str(packet.get("work_type") or "development")


def build_repair_runtime_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "work_type": "repair",
        "objective": packet.get("repair_objective", ""),
        "original_objective": packet.get("original_objective") or packet.get("objective", ""),
        "verification_failure": packet.get("failure_reason", ""),
        "patch_id": packet.get("patch_id", ""),
        "verification_id": packet.get("verification_id") or packet.get("source_verification_id", ""),
        "repo_evidence": ensure_list(
            packet.get("repo_evidence") or packet.get("evidence")
        ),
        "dependency_hints": ensure_list(packet.get("dependency_hints")),
        "target_files": ensure_list(packet.get("target_files")),
        "constraints": {
            "proposal_only": True,
            "no_file_writes": True,
            "no_promotion": True,
            "no_commit": True,
            "must_preserve_original_objective": True,
            "must_address_verification_failure": True,
        },
    }


def normalize_devworker_packet(packet: dict[str, Any]) -> dict[str, Any]:
    work_type = get_work_type(packet)

    if work_type == "repair":
        return build_repair_runtime_packet(packet)

    return packet

#-----------------------------------------------------#

if __name__ == "__main__":
    import json

    test_payload = {
        "objective": "Propose how to make DevWorker consume Repository Agent evidence before planning.",
        "target_files": [
            "agents/dev_worker_agent.py",
            "chair.py",
        ],
        "repo_evidence": [
            {
                "file": "agents/dev_worker_agent.py",
                "lines": "1-80",
                "summary": "DevWorker loads dev_worker_system.txt and builds an LLM prompt."
            },
            {
                "file": "chair.py",
                "lines": "160-210",
                "summary": "Chair executes ready steps and dispatches agents."
            }
        ],
        "dependency_hints": [
            {
                "name": "services.llm_service.invoke_llm",
                "resolved": True,
                "reason": "Used to call the configured model route."
            }
        ],
        "constraints": {
            "proposal_only": True,
            "no_file_writes": True,
            "must_use_repository_evidence": True,
            "must_cite_lines_when_available": True,
        },
    }

    result = run(test_payload)
    print(json.dumps(result, indent=2))