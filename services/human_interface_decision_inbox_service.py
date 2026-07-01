from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.human_consultation_service import HumanConsultationService
from services.proposal_service import ProposalService


class HumanInterfaceDecisionInboxService:
    """Read-only Human Interface Adapter projection for governed decisions.

    This service composes existing Ageix system-of-record data into a
    summary-first Decision Inbox. It intentionally does not create approval
    state, trigger workers, call capability execution, write audit records, or
    mutate proposals, ADRs, evidence, validation files, decision traces, Git, or
    architecture registry data.
    """

    REQUIRED_PROJECT_ID = "Ageix"
    GOVERNING_ARTIFACT_IDS = [
        "EVPKG-298023C1EE14",
        "ADR-0017",
        "ADR-1CE374A025B2",
        "PRIN-0007",
        "INTENT-0008",
        "ARCHREV-2F16C935631A",
        "ARCHFIND-A8A100EB0C79",
        "ARCH-AGEIX-GOVERNANCEPLATFORM-CONSULTATIONFRAMEWORK",
    ]
    GOVERNING_ARCHITECTURE_FILES = [
        ".ageix/architecture/human_interface_architecture.json",
        ".ageix/architecture/human_interface_foundation.md",
        ".ageix/architecture/open_webui_integration_assessment.md",
        ".ageix/architecture/open_webui_adapter_pattern.json",
        ".ageix/architecture/validation/sprint_26_human_interface_validation.md",
        ".ageix/architecture/validation/sprint_26_1_open_webui_integration_validation.md",
    ]
    PENDING_PROPOSAL_STATUSES = {
        "draft",
        "submitted",
        "awaiting_evidence",
        "awaiting_consultation",
        "consultation_submitted",
        "under_review",
    }
    PENDING_ADR_STATUSES = {"draft", "proposed"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.human_consultations = HumanConsultationService(self.repo_root)

    def get_decision_inbox(self, project_id: str | None) -> dict[str, Any]:
        if project_id != self.REQUIRED_PROJECT_ID:
            return self._access_denied(project_id)

        records: list[dict[str, Any]] = []
        source_status: dict[str, Any] = {}

        proposals, proposal_status = self._pending_proposals(project_id)
        records.extend(proposals)
        source_status["pending_proposals"] = proposal_status

        adrs, adr_status = self._pending_architecture_decisions(project_id)
        records.extend(adrs)
        source_status["pending_architecture_decisions"] = adr_status

        consultations, consultation_status = self._pending_human_consultations(project_id)
        records.extend(consultations)
        source_status["pending_human_consultations"] = consultation_status

        validations, validation_status = self._validation_results(project_id)
        records.extend(validations)
        source_status["validation_results"] = validation_status

        traces, trace_status = self._recent_decision_traces(project_id)
        records.extend(traces)
        source_status["recent_decision_traces"] = trace_status

        evidence, evidence_status = self._evidence_links(project_id)
        records.extend(evidence)
        source_status["evidence_links"] = evidence_status

        records.sort(key=lambda item: str(item.get("sort_timestamp") or ""), reverse=True)
        for record in records:
            record.pop("sort_timestamp", None)

        return {
            "summary": {
                "project_id": project_id,
                "mode": "read_only",
                "record_count": len(records),
                "source_count": len(source_status),
                "status_label": "decision_inbox_available",
                "mutation_controls_exposed": False,
                "consultation_choices_available": True,
                "consultation_state_owner": "Ageix",
            },
            "project_id": project_id,
            "adapter": "human_interface_decision_inbox",
            "read_only": True,
            "generated_at": self._now(),
            "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
            "governing_architecture_files": list(self.GOVERNING_ARCHITECTURE_FILES),
            "records": records,
            "source_status": source_status,
        }

    def _access_denied(self, project_id: str | None) -> dict[str, Any]:
        reason = "project_id_required" if not project_id else "project_scope_denied"
        return {
            "summary": {
                "project_id": project_id,
                "mode": "read_only",
                "record_count": 0,
                "status_label": "access_denied",
                "mutation_controls_exposed": False,
            },
            "success": False,
            "error": reason,
            "project_id": project_id,
            "required_project_id": self.REQUIRED_PROJECT_ID,
            "read_only": True,
            "records": [],
        }

    def _pending_proposals(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            proposals = ProposalService(self.repo_root).list_proposals(project_id=project_id)
        except Exception as exc:
            return [], self._source_error(exc)
        records = []
        for proposal in proposals:
            payload = proposal.model_dump(mode="json")
            status = str(payload.get("status") or "")
            if status not in self.PENDING_PROPOSAL_STATUSES:
                continue
            proposal_id = payload.get("proposal_id")
            records.append({
                "record_type": "pending_proposal",
                "record_id": proposal_id,
                "summary": payload.get("objective") or "Governed proposal awaiting decision review.",
                "status_label": status,
                "next_governed_action_label": "respond_to_ageix_human_consultation_choice",
                "trace_ids": [],
                "evidence_links": list(payload.get("linked_evidence") or []),
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "consultation_metadata": self.human_consultations.decision_choices_for_record(
                    target_record_type="proposal",
                    target_record_id=str(proposal_id or ""),
                ),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/manifests/proposals",
                    "proposal_id": proposal_id,
                },
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
                "sort_timestamp": payload.get("updated_at") or payload.get("created_at") or "",
            })
        return records, {"status": "available", "count": len(records)}

    def _pending_architecture_decisions(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            result = ArchitectureDecisionRecordService(self.repo_root).list_adrs(project_id=project_id, limit=200)
        except Exception as exc:
            return [], self._source_error(exc)
        records = []
        for adr in result.get("adrs", []):
            status = str(adr.get("status") or "")
            if status not in self.PENDING_ADR_STATUSES:
                continue
            adr_id = adr.get("adr_id")
            records.append({
                "record_type": "pending_architecture_decision",
                "record_id": adr_id,
                "summary": adr.get("title") or adr.get("decision") or "Architecture decision awaiting governance.",
                "status_label": status,
                "next_governed_action_label": "respond_to_ageix_human_consultation_choice",
                "trace_ids": [adr.get("decision_trace_id")] if adr.get("decision_trace_id") else [],
                "evidence_links": list(adr.get("evidence_package_ids") or []),
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "consultation_metadata": self.human_consultations.decision_choices_for_record(
                    target_record_type="adr",
                    target_record_id=str(adr_id or ""),
                ),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/architecture/adrs",
                    "adr_id": adr_id,
                    "proposal_id": adr.get("proposal_id"),
                },
                "created_at": adr.get("created_at"),
                "updated_at": adr.get("approved_at") or adr.get("created_at"),
                "sort_timestamp": adr.get("approved_at") or adr.get("created_at") or "",
            })
        return records, {"status": "available", "count": len(records)}

    def _pending_human_consultations(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            requests = self.human_consultations.list_requests(project_id=project_id, status="pending")
        except Exception as exc:
            return [], self._source_error(exc)
        records = []
        for request in requests[:50]:
            payload = request.model_dump(mode="json")
            context = payload.get("context") or {}
            records.append({
                "record_type": "pending_human_consultation",
                "record_id": payload.get("consultation_id"),
                "summary": payload.get("summary") or payload.get("question") or "Human consultation awaiting Chair choice.",
                "status_label": payload.get("status") or "pending",
                "next_governed_action_label": "submit_constrained_choice_via_human_consultation_respond",
                "trace_ids": list(context.get("trace_ids") or []),
                "evidence_links": list(context.get("evidence_links") or []),
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "consultation_metadata": {
                    "consultation_id": payload.get("consultation_id"),
                    "consultation_type": payload.get("consultation_type"),
                    "question": payload.get("question"),
                    "choices": list(payload.get("choices") or []),
                    "system_of_record": "Ageix",
                    "state_owner": "Ageix",
                    "mutation_controls_exposed": False,
                },
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/human_consultations",
                    "consultation_id": payload.get("consultation_id"),
                    "target_record_type": context.get("target_record_type"),
                    "target_record_id": context.get("target_record_id"),
                },
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
                "sort_timestamp": payload.get("updated_at") or payload.get("created_at") or "",
            })
        return records, {"status": "available", "count": len(records)}

    def _validation_results(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        validation_root = self.repo_root / ".ageix" / "architecture" / "validation"
        if not validation_root.exists():
            return [], {"status": "not_present", "count": 0}
        records = []
        for path in sorted(validation_root.glob("*"), key=lambda item: item.name, reverse=True)[:25]:
            if not path.is_file() or path.suffix.lower() not in {".md", ".json"}:
                continue
            records.append({
                "record_type": "validation_result",
                "record_id": path.stem,
                "summary": f"Validation artifact available: {path.name}",
                "status_label": "available",
                "next_governed_action_label": "inspect_validation_artifact_if_needed",
                "trace_ids": [],
                "evidence_links": [],
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/architecture/validation",
                    "path": self._relative(path),
                },
                "created_at": None,
                "updated_at": None,
                "sort_timestamp": path.name,
            })
        return records, {"status": "available", "count": len(records)}

    def _recent_decision_traces(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        index_path = self.repo_root / ".ageix" / "decision_traces" / "index.json"
        if not index_path.exists():
            return [], {"status": "not_present", "count": 0}
        try:
            traces = json.loads(index_path.read_text(encoding="utf-8")).get("traces", [])
        except Exception as exc:
            return [], self._source_error(exc)
        records = []
        for trace in sorted(traces, key=lambda item: str(item.get("created_at") or ""), reverse=True)[:25]:
            trace_project_id = str(trace.get("project_id") or "")
            if trace_project_id and trace_project_id != project_id:
                continue
            records.append({
                "record_type": "recent_decision_trace",
                "record_id": trace.get("trace_id"),
                "summary": trace.get("decision_summary") or "Decision trace available.",
                "status_label": str(trace.get("outcome") or "recorded"),
                "next_governed_action_label": "inspect_trace_if_needed",
                "trace_ids": [trace.get("trace_id")] if trace.get("trace_id") else [],
                "evidence_links": list(trace.get("evidence_package_ids") or []),
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/decision_traces/index.json",
                    "decision_id": trace.get("decision_id"),
                    "proposal_id": trace.get("proposal_id"),
                },
                "created_at": trace.get("created_at"),
                "updated_at": trace.get("created_at"),
                "sort_timestamp": trace.get("created_at") or "",
            })
        return records, {"status": "available", "count": len(records)}

    def _evidence_links(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            entries = EvidencePackageIndexService(self.repo_root).list_entries()
        except Exception as exc:
            return [], self._source_error(exc)
        records = []
        for entry in sorted(entries, key=lambda item: str(item.get("created_at") or ""), reverse=True)[:25]:
            entry_project_id = str(entry.get("project_id") or "")
            if entry_project_id and entry_project_id != project_id:
                continue
            package_id = entry.get("package_id")
            if not package_id:
                continue
            records.append({
                "record_type": "evidence_link",
                "record_id": package_id,
                "summary": entry.get("objective") or "Evidence package available.",
                "status_label": str(entry.get("freshness_status") or "available"),
                "next_governed_action_label": "inspect_evidence_package_if_needed",
                "trace_ids": [],
                "evidence_links": [package_id],
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/evidence_packages/index.json",
                    "proposal_id": entry.get("proposal_id"),
                    "evidence_plan_id": entry.get("evidence_plan_id"),
                },
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("last_freshness_check_at") or entry.get("created_at"),
                "sort_timestamp": entry.get("last_freshness_check_at") or entry.get("created_at") or "",
            })
        return records, {"status": "available", "count": len(records)}

    def _source_error(self, exc: Exception) -> dict[str, Any]:
        return {"status": "safe_error", "count": 0, "error": str(exc)}

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return str(path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
