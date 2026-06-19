from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition


def _consultation_root(repo_root: Path) -> Path:
    return repo_root / ".ageix" / "manifests" / "consultations"


def _summary(session: dict[str, Any]) -> dict[str, Any]:
    proposal = session.get("proposal", {})
    return {
        "consultation_id": session.get("consultation_id"),
        "status": session.get("status"),
        "consultation_type": proposal.get("consultation_type"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "evidence_request_count": len(session.get("evidence_requests", [])),
        "response_count": len(session.get("consultation_responses", [])),
    }


def register_capabilities(repo_root: Path):
    def consultation_list(arguments: dict[str, Any]) -> dict[str, Any]:
        limit = int(arguments.get("limit") or 20)
        sessions = []
        root = _consultation_root(repo_root)
        if root.exists():
            for path in sorted(root.glob("*/session.json"), reverse=True)[:limit]:
                sessions.append(_summary(json.loads(path.read_text(encoding="utf-8"))))
        return {"success": True, "result": {"consultations": sessions}, "metadata": {"source": "consultation_sessions"}}

    def consultation_get(arguments: dict[str, Any]) -> dict[str, Any]:
        consultation_id = str(arguments.get("consultation_id") or "")
        if not consultation_id:
            return {"success": False, "result": {}, "error": "consultation_id_required"}
        path = _consultation_root(repo_root) / consultation_id / "session.json"
        if not path.exists():
            return {"success": False, "result": {}, "error": "consultation_not_found"}
        session = json.loads(path.read_text(encoding="utf-8"))
        result = {
            **_summary(session),
            "approval": session.get("approval", {}),
            "consultation_responses": session.get("consultation_responses", []),
            "evidence_requests": session.get("evidence_requests", []),
            "evidence_responses": [
                {k: v for k, v in response.items() if k != "payload"}
                for response in session.get("evidence_responses", [])
            ],
        }
        return {"success": True, "result": result, "metadata": {"source": "consultation_sessions"}}

    return [
        (CapabilityDefinition(
            capability_id="consultation.list",
            category="consultation",
            access_level="read",
            handler="consultation.list",
            description="List governed consultation summaries.",
        ), consultation_list),
        (CapabilityDefinition(
            capability_id="consultation.get",
            category="consultation",
            access_level="read",
            handler="consultation.get",
            description="Return one governed consultation result.",
        ), consultation_get),
    ]
