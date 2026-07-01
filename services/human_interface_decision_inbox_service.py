from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.proposal_service import ProposalService


class HumanInterfaceDecisionInboxService:
    """Read-only Human Interface Adapter projection for governed decisions.

    This service composes existing Ageix system-of-record data into a
    summary-first Decision Inbox and Decision Detail view. It intentionally does
    not create approval state, trigger workers, call capability execution, write
    audit records, or mutate proposals, ADRs, evidence, validation files,
    decision traces, Git, or architecture registry data.
    """

    REQUIRED_PROJECT_ID = "Ageix"
    GOVERNING_ARTIFACT_IDS = [
        "EVPKG-298023C1EE14",
        "ADR-0017",
        "ADR-1CE374A025B2",
        "PRIN-0007",
        "INTENT-0008",
        "ARCHREV-2F16C935631A",
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
    ACTION_CONTRACTS = [
        {
            "action": "approve",
            "label": "Approve through governed Ageix capability path",
            "sprint_26_3_executable": False,
            "required_fields": ["project_id", "target_record_id", "target_record_type", "rationale"],
            "required_controls": [
                "project_id_must_equal_Ageix",
                "authenticated_identity_required",
                "capability_authorization_required",
                "decision_trace_update_required",
                "audit_linkage_required",
                "validation_evidence_required_where_applicable",
            ],
        },
        {
            "action": "reject",
            "label": "Reject through governed Ageix capability path",
            "sprint_26_3_executable": False,
            "required_fields": ["project_id", "target_record_id", "target_record_type", "rationale"],
            "required_controls": [
                "project_id_must_equal_Ageix",
                "authenticated_identity_required",
                "capability_authorization_required",
                "decision_trace_update_required",
                "audit_linkage_required",
                "validation_evidence_required_where_applicable",
            ],
        },
        {
            "action": "defer",
            "label": "Defer through governed Ageix capability path",
            "sprint_26_3_executable": False,
            "required_fields": ["project_id", "target_record_id", "target_record_type", "rationale"],
            "required_controls": [
                "project_id_must_equal_Ageix",
                "authenticated_identity_required",
                "capability_authorization_required",
                "decision_trace_update_required",
                "audit_linkage_required",
            ],
        },
        {
            "action": "request_changes",
            "label": "Request changes through governed Ageix capability path",
            "sprint_26_3_executable": False,
            "required_fields": ["project_id", "target_record_id", "target_record_type", "rationale"],
            "required_controls": [
                "project_id_must_equal_Ageix",
                "authenticated_identity_required",
                "capability_authorization_required",
                "decision_trace_update_required",
                "audit_linkage_required",
                "validation_evidence_required_where_applicable",
            ],
        },
        {
            "action": "add_comment/rationale",
            "label": "Add rationale or comment through governed Ageix capability path",
            "sprint_26_3_executable": False,
            "required_fields": ["project_id", "target_record_id", "target_record_type", "rationale"],
            "required_controls": [
                "project_id_must_equal_Ageix",
                "authenticated_identity_required",
                "capability_authorization_required",
                "decision_trace_update_required",
                "audit_linkage_required",
            ],
        },
    ]

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

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

    def get_decision_detail(self, decision_id: str, project_id: str | None) -> dict[str, Any]:
        if project_id != self.REQUIRED_PROJECT_ID:
            denied = self._access_denied(project_id)
            denied["decision_id"] = decision_id
            return denied

        inbox = self.get_decision_inbox(project_id)
        records = list(inbox.get("records") or [])
        record = self._find_record(records, decision_id)
        if not record:
            return {
                "summary": {
                    "project_id": project_id,
                    "mode": "read_only",
                    "decision_id": decision_id,
                    "record_count": 0,
                    "status_label": "decision_detail_not_found",
                    "mutation_controls_exposed": False,
                },
                "success": False,
                "error": "decision_detail_not_found",
                "project_id": project_id,
                "decision_id": decision_id,
                "read_only": True,
                "records": [],
            }

        detail = self._source_detail(record)
        record_id = str(record.get("record_id") or decision_id)
        record_type = str(record.get("record_type") or "unknown")
        trace_links = [item for item in record.get("trace_ids", []) if item]
        evidence_links = [item for item in record.get("evidence_links", []) if item]
        validation_links = self._validation_links(record, detail)
        action_labels = self._available_action_labels(record_type)

        return {
            "summary": {
                "project_id": project_id,
                "mode": "read_only",
                "decision_id": decision_id,
                "record_id": record_id,
                "record_type": record_type,
                "status_label": "decision_detail_available",
                "mutation_controls_exposed": False,
                "action_contracts_executable": False,
            },
            "project_id": project_id,
            "adapter": "human_interface_decision_detail",
            "read_only": True,
            "generated_at": self._now(),
            "decision_id": decision_id,
            "record_id": record_id,
            "record_type": record_type,
            "status": record.get("status_label"),
            "title": self._title(record, detail),
            "objective": self._objective(record, detail),
            "summary_text": record.get("summary"),
            "governing_artifact_ids": list(dict.fromkeys([
                *self.GOVERNING_ARTIFACT_IDS,
                *[item for item in record.get("governing_artifact_ids", []) if item],
            ])),
            "governing_architecture_files": list(self.GOVERNING_ARCHITECTURE_FILES),
            "evidence_links": evidence_links,
            "validation_links": validation_links,
            "decision_trace_links": trace_links,
            "available_next_governed_action_labels": action_labels,
            "rationale_requirement": {
                "required": True,
                "minimum_expectation": "explicit_human_rationale_for_any_future_governed_action",
            },
            "authority_requirement": {
                "project_id": self.REQUIRED_PROJECT_ID,
                "authenticated_identity_required": True,
                "capability_authorization_required": True,
                "ageix_system_of_record_required": True,
                "open_webui_shell_only": True,
            },
            "governed_action_contracts": self._action_contracts_for(record_id, record_type),
            "source": record.get("source", {}),
            "source_record": record,
            "source_detail": detail,
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
            records.append({
                "record_type": "pending_proposal",
                "record_id": payload.get("proposal_id"),
                "summary": payload.get("objective") or "Governed proposal awaiting decision review.",
                "status_label": status,
                "next_governed_action_label": "review_through_existing_governance_path",
                "trace_ids": [],
                "evidence_links": list(payload.get("linked_evidence") or []),
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/manifests/proposals",
                    "proposal_id": payload.get("proposal_id"),
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
            records.append({
                "record_type": "pending_architecture_decision",
                "record_id": adr.get("adr_id"),
                "summary": adr.get("title") or adr.get("decision") or "Architecture decision awaiting governance.",
                "status_label": status,
                "next_governed_action_label": "review_adr_proposal_through_existing_governance_path",
                "trace_ids": [adr.get("decision_trace_id")] if adr.get("decision_trace_id") else [],
                "evidence_links": list(adr.get("evidence_package_ids") or []),
                "governing_artifact_ids": list(self.GOVERNING_ARTIFACT_IDS),
                "source": {
                    "system_of_record": "Ageix",
                    "store": ".ageix/architecture/adrs",
                    "adr_id": adr.get("adr_id"),
                    "proposal_id": adr.get("proposal_id"),
                },
                "created_at": adr.get("created_at"),
                "updated_at": adr.get("approved_at") or adr.get("created_at"),
                "sort_timestamp": adr.get("approved_at") or adr.get("created_at") or "",
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

    def _find_record(self, records: list[dict[str, Any]], decision_id: str) -> dict[str, Any] | None:
        target = str(decision_id or "")
        for record in records:
            source = dict(record.get("source") or {})
            candidates = {
                str(record.get("record_id") or ""),
                str(source.get("decision_id") or ""),
                str(source.get("proposal_id") or ""),
                str(source.get("adr_id") or ""),
                Path(str(source.get("path") or "")).stem,
            }
            if target in candidates:
                return record
        return None

    def _source_detail(self, record: dict[str, Any]) -> dict[str, Any]:
        source = dict(record.get("source") or {})
        record_type = str(record.get("record_type") or "")
        try:
            if record_type == "pending_proposal" and source.get("proposal_id"):
                return ProposalService(self.repo_root).get_proposal(str(source["proposal_id"])).model_dump(mode="json")
            if record_type == "pending_architecture_decision" and source.get("adr_id"):
                return ArchitectureDecisionRecordService(self.repo_root).get_adr(str(source["adr_id"]))
            if record_type == "validation_result" and source.get("path"):
                path = self.repo_root / str(source["path"])
                if path.exists() and path.is_file():
                    return {
                        "path": self._relative(path),
                        "artifact_name": path.name,
                        "excerpt": path.read_text(encoding="utf-8")[:2000],
                    }
            if record_type == "recent_decision_trace":
                return self._decision_trace_detail(record)
            if record_type == "evidence_link" and record.get("record_id"):
                return self._evidence_detail(str(record["record_id"]))
        except Exception as exc:
            return {"status": "safe_error", "error": str(exc)}
        return {}

    def _decision_trace_detail(self, record: dict[str, Any]) -> dict[str, Any]:
        index_path = self.repo_root / ".ageix" / "decision_traces" / "index.json"
        if not index_path.exists():
            return {}
        traces = json.loads(index_path.read_text(encoding="utf-8")).get("traces", [])
        source = dict(record.get("source") or {})
        target_trace = str(record.get("record_id") or "")
        target_decision = str(source.get("decision_id") or "")
        for trace in traces:
            if str(trace.get("trace_id") or "") == target_trace or str(trace.get("decision_id") or "") == target_decision:
                return dict(trace)
        return {}

    def _evidence_detail(self, package_id: str) -> dict[str, Any]:
        for entry in EvidencePackageIndexService(self.repo_root).list_entries():
            if str(entry.get("package_id") or "") == package_id:
                return dict(entry)
        return {}

    def _title(self, record: dict[str, Any], detail: dict[str, Any]) -> str:
        return str(
            detail.get("title")
            or detail.get("objective")
            or record.get("summary")
            or record.get("record_id")
            or "Decision detail"
        )

    def _objective(self, record: dict[str, Any], detail: dict[str, Any]) -> str | None:
        objective = detail.get("objective") or detail.get("decision_summary") or record.get("summary")
        return str(objective) if objective else None

    def _validation_links(self, record: dict[str, Any], detail: dict[str, Any]) -> list[str]:
        links = []
        source = dict(record.get("source") or {})
        if record.get("record_type") == "validation_result" and source.get("path"):
            links.append(str(source["path"]))
        for key in ("validation_links", "validation_evidence", "validation_artifact_ids"):
            value = detail.get(key)
            if isinstance(value, list):
                links.extend(str(item) for item in value if item)
            elif value:
                links.append(str(value))
        return list(dict.fromkeys(links))

    def _available_action_labels(self, record_type: str) -> list[str]:
        if record_type in {"pending_proposal", "pending_architecture_decision"}:
            return [contract["action"] for contract in self.ACTION_CONTRACTS]
        return ["defer", "add_comment/rationale"]

    def _action_contracts_for(self, record_id: str, record_type: str) -> list[dict[str, Any]]:
        contracts = []
        for contract in self.ACTION_CONTRACTS:
            contracts.append({
                **contract,
                "target_record_id": record_id,
                "target_record_type": record_type,
                "project_id": self.REQUIRED_PROJECT_ID,
                "transport": "not_exposed_by_human_interface_adapter_in_sprint_26_3",
            })
        return contracts

    def _source_error(self, exc: Exception) -> dict[str, Any]:
        return {"status": "safe_error", "count": 0, "error": str(exc)}

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return str(path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
