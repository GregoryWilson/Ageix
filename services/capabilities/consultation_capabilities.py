from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from models.consultation_recommendation import ConsultationDisposition
from models.consultation_response import ConsultationResponse
from services.proposal_service import ProposalService
from services.consultation_evidence_review_service import ConsultationEvidenceReviewService


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


    def consultation_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(arguments.get("proposal_id") or "")
        consultation_type = str(arguments.get("consultation_type") or "")
        if not proposal_id:
            return {"success": False, "result": {}, "error": "proposal_id_required"}
        if not consultation_type:
            return {"success": False, "result": {}, "error": "consultation_type_required"}
        consultation_id = str(arguments.get("consultation_id") or f"EXT-{proposal_id}-{consultation_type}")
        response = ConsultationResponse(
            participant_id=str(arguments.get("agent_id") or "external_agent"),
            participant_type=str(arguments.get("participant_type") or "gpt"),
            response_type=consultation_type,
            recommendation=str(arguments.get("summary") or arguments.get("recommendation") or ""),
            confidence=float(arguments.get("confidence") or 0.0),
            disposition=ConsultationDisposition(str(arguments.get("disposition") or "caution")),
            evidence_sufficient=bool(arguments.get("evidence_sufficient", False)),
            findings=arguments.get("findings") or [],
            concerns=arguments.get("risks") or arguments.get("concerns") or [],
            suggested_improvements=arguments.get("recommendations") or arguments.get("suggested_improvements") or [],
            metadata={
                "proposal_id": proposal_id,
                "consultation_id": consultation_id,
                "session_id": arguments.get("session_id"),
                "source": "external_agent_submitted_consultation",
                "user_guidance": arguments.get("user_guidance") or [],
                "supporting_evidence": arguments.get("supporting_evidence") or [],
                **(arguments.get("metadata") or {}),
            },
        )
        root = _consultation_root(repo_root) / consultation_id
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "consultation_id": consultation_id,
            "status": "submitted",
            "proposal_id": proposal_id,
            "consultation_type": consultation_type,
            "external_agent_submitted": True,
            "response": response.model_dump(),
        }
        (root / "session.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        ProposalService(repo_root).link_consultation(proposal_id, consultation_id)
        ProposalService(repo_root).update_status(proposal_id, "consultation_submitted")
        return {"success": True, "result": payload, "metadata": {"proposal_id": proposal_id, "consultation_id": consultation_id}}

    def consultation_details(arguments: dict[str, Any]) -> dict[str, Any]:
        consultation_id = str(arguments.get("consultation_id") or "")
        if not consultation_id:
            return {"success": False, "result": {}, "error": "consultation_id_required"}
        try:
            session = ConsultationEvidenceReviewService(repo_root).details(consultation_id)
        except FileNotFoundError:
            return {"success": False, "result": {}, "error": "consultation_not_found"}
        result = {
            **_summary(session),
            "proposal_id": session.get("proposal_id"),
            "external_agent_submitted": session.get("external_agent_submitted", False),
            "response": session.get("response"),
            "review": session.get("review", {}),
            "review_recommendations": session.get("review_recommendations", []),
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
            capability_id="consultation.submit",
            category="consultation",
            access_level="governed_read",
            handler="consultation.submit",
            description="Submit external-agent consultation evidence for Chair review; does not approve proposals.",
            requires_proposal=True,
        ), consultation_submit),
        (CapabilityDefinition(
            capability_id="consultation.list",
            category="consultation",
            access_level="read",
            handler="consultation.list",
            description="List governed consultation summaries.",
        ), consultation_list),
        (CapabilityDefinition(
            capability_id="consultation.details",
            category="consultation",
            access_level="read",
            handler="consultation.details",
            description="Return one governed consultation result by ID.",
        ), consultation_details),
    ]
