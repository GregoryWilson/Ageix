from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.evidence_access_proposal import EvidenceAccessDecision, EvidenceAccessProposal, EvidenceRequestItem
from services.agent_profile_service import AgentProfileService
from services.approval_request_service import ApprovalRequestService
from services.current_project_resolution_service import CurrentProjectResolutionService
from services.code_context_extractor import CodeContextExtractor
from services.controls_service import ControlsService
from services.project_registry_service import ProjectRegistryService
from services.repository_inventory_service import RepositoryInventoryService
from services.target_resolution_service import TargetResolutionService


class EvidenceAccessProposalService:
    """Chair-governed proposal evaluator for external agent repository evidence requests."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.controls = ControlsService(self.repo_root).get_raw_config().get("agent_capabilities", {})
        self.profile_service = AgentProfileService(self.repo_root)
        self.target_resolution = TargetResolutionService(self.repo_root)
        self.inventory_service = RepositoryInventoryService(self.repo_root)
        self.extractor = CodeContextExtractor(self.repo_root)
        self.proposal_root = self.repo_root / ".ageix" / "manifests" / "evidence_access_proposals"
        self.project_resolution = CurrentProjectResolutionService(self.repo_root)
        self.approvals = ApprovalRequestService(self.repo_root)

    def evaluate(self, proposal: EvidenceAccessProposal) -> EvidenceAccessDecision:
        proposal.project_id = self._resolve_project_id(proposal)
        budget = self.profile_service.evidence_budget(proposal.agent_id, self.controls)
        hard = self._hard_limits()
        profile = self.profile_service.get_profile(proposal.agent_id)
        reasons: list[str] = []
        approved: list[dict[str, Any]] = []
        denied: list[dict[str, Any]] = []
        total_lines = 0
        resolved_files = 0
        human_required = False

        if not proposal.requested_evidence:
            decision = EvidenceAccessDecision(
                proposal_id=proposal.proposal_id,
                decision="denied",
                denied_evidence=[],
                reasons=["evidence_access_proposal_requires_requested_evidence"],
                metadata=self._metadata(proposal, profile.reputation_level, budget),
            )
            self._persist(proposal, decision)
            return decision

        project_error = self._validate_project(proposal.project_id)
        if project_error:
            decision = EvidenceAccessDecision(
                proposal_id=proposal.proposal_id,
                decision="denied",
                denied_evidence=[{"reason": project_error}],
                reasons=[project_error],
                metadata=self._metadata(proposal, profile.reputation_level, budget),
            )
            self._persist(proposal, decision)
            return decision

        if len(proposal.requested_evidence) > hard["max_items"]:
            reasons.append("evidence_request_exceeds_hard_item_limit")
            if not self._human_override(proposal):
                human_required = True

        for item in proposal.requested_evidence:
            item_denial = self._validate_item(item)
            if item_denial:
                reason, details = item_denial
                denied.append(self._denied_item(item, reason, details))
                continue

            resolution = self.target_resolution.resolve_target(item.path)
            if resolution.planner_revisit_required or not resolution.resolved_target:
                denied.append(self._denied_item(item, "target_resolution_failed", resolution.model_dump()))
                continue

            if item.type == "directory_summary" and resolution.target_type != "directory":
                denied.append(self._denied_item(item, "directory_summary_requires_directory_target", resolution.model_dump()))
                continue
            if item.type != "directory_summary" and resolution.target_type != "file":
                denied.append(self._denied_item(item, "file_evidence_requires_file_target", resolution.model_dump()))
                continue

            payload = self._fetch_item(item, resolution.resolved_target)
            line_count = int(payload.get("line_count", 0))
            resolved_files += 1 if item.type != "directory_summary" else int(payload.get("file_count", 0))
            total_lines += line_count
            approved.append({
                "type": item.type,
                "path": resolution.resolved_target,
                "requested_path": item.path,
                "reason": item.reason,
                "symbol": item.symbol,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "resolution": resolution.model_dump(),
                **payload,
            })

        if resolved_files > budget["max_files"] or total_lines > budget["max_lines"] or len(proposal.requested_evidence) > budget["max_items"]:
            reasons.append("evidence_request_exceeds_reputation_budget")
            if not self._human_override(proposal):
                human_required = True
        if resolved_files > hard["max_files"] or total_lines > hard["max_lines"]:
            reasons.append("evidence_request_exceeds_hard_evidence_limit")
            if not self._human_override(proposal):
                human_required = True

        approval_id = None
        if human_required:
            approved = []
            decision_value = "human_approval_required"
            approval = self.approvals.create_request(
                proposal_id=proposal.proposal_id,
                reason=", ".join(reasons) or "human approval required",
                requested_by=proposal.agent_id,
                request_type="evidence_expansion",
            )
            approval_id = approval.approval_id
        elif approved and not denied:
            decision_value = "approved"
        elif approved and denied:
            decision_value = "approved"
            reasons.append("partial_evidence_approval")
        else:
            decision_value = "denied"
            if not reasons:
                reasons.append("no_evidence_items_approved")

        decision = EvidenceAccessDecision(
            proposal_id=proposal.proposal_id,
            decision=decision_value,
            approved_evidence=approved,
            denied_evidence=denied,
            human_approval_required=human_required,
            reasons=reasons,
            metadata={
                **self._metadata(proposal, profile.reputation_level, budget),
                "target_resolution_used": True,
                "evidence_broker_used": True,
                "resolved_files": resolved_files,
                "total_lines": total_lines,
                "hard_limits": hard,
                **({"approval_id": approval_id} if approval_id else {}),
            },
        )
        self._persist(proposal, decision)
        return decision

    def _resolve_project_id(self, proposal: EvidenceAccessProposal) -> str:
        project_id = proposal.project_id or None
        if project_id in {"Ageix", "ageix"}:
            try:
                return self.project_resolution.resolve_project_id(project_id, proposal.session_id or None)
            except Exception:
                return str(project_id)
        return self.project_resolution.resolve_project_id(project_id, proposal.session_id or None)

    def _validate_project(self, project_id: str) -> str | None:
        try:
            ProjectRegistryService(self.repo_root).get_project(project_id)
        except Exception:
            if project_id in {"Ageix", "ageix"}:
                return None
            return "unknown_project_id"
        return None

    def _validate_item(self, item: EvidenceRequestItem) -> tuple[str, dict[str, Any]] | None:
        scores = self._justification_scores(item)
        min_words = int(self.controls.get("min_reason_words", 3))
        if scores["word_count"] < min_words or scores["specificity_score"] < 0.5:
            return "evidence_request_reason_too_sparse", {
                "specificity_score": scores["specificity_score"],
                "relevance_score": scores["relevance_score"],
                "scope_score": scores["scope_score"],
                "overall_score": scores["overall_score"],
                "required_minimum": 0.5,
                "minimum_reason_words": min_words,
                "message": "Explain why this exact path and scope are needed for the stated objective.",
            }
        normalized = Path(item.path)
        if normalized.is_absolute() or ".." in normalized.parts:
            return "evidence_request_path_must_be_repo_relative", {"message": "Evidence paths must be repository-relative and cannot traverse upward."}
        return None

    def _justification_scores(self, item: EvidenceRequestItem) -> dict[str, Any]:
        words = [word.strip(".,;:()[]{}\"'").lower() for word in item.reason.split() if word.strip()]
        unique = set(words)
        specificity_terms = {"exact", "specific", "implementation", "symbol", "line", "class", "function", "validate", "governance", "target", "evidence"}
        scope_terms = {"file", "directory", "section", "symbol", "lines", "range", "only", "because", "needed", "review"}
        specificity = min(1.0, (len(unique & specificity_terms) / 2.0) + (0.2 if item.symbol or item.start_line else 0.0))
        relevance = min(1.0, max(0.2, len(words) / 8.0))
        scope = min(1.0, (len(unique & scope_terms) / 2.0) + (0.2 if item.type in {"symbol", "line_range", "section"} else 0.0))
        overall = round((specificity + relevance + scope) / 3.0, 3)
        return {
            "word_count": len(words),
            "specificity_score": round(specificity, 3),
            "relevance_score": round(relevance, 3),
            "scope_score": round(scope, 3),
            "overall_score": overall,
        }

    def _fetch_item(self, item: EvidenceRequestItem, path: str) -> dict[str, Any]:
        if item.type == "file":
            content = (self.repo_root / path).read_text(encoding="utf-8")
            return {"content": content, "line_count": len(content.splitlines())}
        if item.type in {"section", "symbol"} and item.symbol:
            content = self.extractor.extract_file_slice(path, symbols=[str(item.symbol)], max_lines=self._hard_limits()["max_lines"])
            return {"content": content, "line_count": len(content.splitlines())}
        if item.type in {"line_range", "section"}:
            lines = (self.repo_root / path).read_text(encoding="utf-8").splitlines()
            start = int(item.start_line or 1)
            end = int(item.end_line or start)
            content = "\n".join(lines[start - 1:end])
            return {"content": content + ("\n" if content else ""), "line_count": max(0, end - start + 1)}
        if item.type == "directory_summary":
            inventory = self.inventory_service.inventory()
            prefix = path.rstrip("/") + "/"
            files = [candidate for candidate in inventory.paths if candidate.startswith(prefix)]
            return {"files": files, "file_count": len(files), "line_count": 0}
        raise ValueError(f"Unsupported evidence request type: {item.type}")

    def _hard_limits(self) -> dict[str, int]:
        return {
            "max_files": int(self.controls.get("hard_max_files", 50)),
            "max_lines": int(self.controls.get("hard_max_lines", 20000)),
            "max_items": int(self.controls.get("hard_max_items", 50)),
        }

    def _human_override(self, proposal: EvidenceAccessProposal) -> bool:
        approval = proposal.human_approval or {}
        return bool(approval.get("approved") or approval.get("override"))

    def _metadata(self, proposal: EvidenceAccessProposal, reputation_level: str, budget: dict[str, int]) -> dict[str, Any]:
        return {
            "proposal_id": proposal.proposal_id,
            "project_id": proposal.project_id,
            "agent_id": proposal.agent_id,
            "session_id": proposal.session_id,
            "access_level": "governed_read",
            "approved_by": "chair",
            "agent_reputation_level": reputation_level,
            "reputation_budget": budget,
            "repository_raw_access": False,
        }

    def _denied_item(self, item: EvidenceRequestItem, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"type": item.type, "path": item.path, "reason": reason, "details": details or {}}

    def _persist(self, proposal: EvidenceAccessProposal, decision: EvidenceAccessDecision) -> None:
        path = self.proposal_root / proposal.proposal_id / "proposal.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "proposal": proposal.model_dump(),
            "decision": decision.model_dump(),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
