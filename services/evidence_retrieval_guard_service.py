from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models.capability_audit_record import CapabilityAuditRecord
from services.capability_audit_service import CapabilityAuditService
from services.controls_service import ControlsService


@dataclass(frozen=True)
class RetrievalGuardDecision:
    allowed: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


class EvidenceRetrievalGuardService:
    """Centralized retrieval safety policy for governed evidence access."""

    TEXT_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".md", ".txt", ".toml", ".ini", ".cfg"}
    GENERATED_SUFFIXES = {".patch", ".diff", ".zip", ".tar", ".gz", ".tgz", ".pyc", ".pyo"}
    DEFAULT_DENY_PATTERNS = [
        ".ageix/instance",
        ".ageix/instance/**",
        ".ageix/evidence_packages",
        ".ageix/evidence_packages/**",
        ".pytest_cache",
        ".pytest_cache/**",
        ".git",
        ".git/**",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*.pfx",
        "*.p12",
        "__pycache__",
        "__pycache__/**",
        ".mypy_cache",
        ".mypy_cache/**",
        ".ruff_cache",
        ".ruff_cache/**",
        ".venv",
        ".venv/**",
        "venv",
        "venv/**",
    ]

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        raw = ControlsService(self.repo_root).get_raw_config()
        evidence_package = raw.get("evidence_package", {}) if isinstance(raw, dict) else {}
        configured = evidence_package.get("retrieval_deny_patterns") or []
        self.deny_patterns = [*self.DEFAULT_DENY_PATTERNS, *[str(item) for item in configured]]
        self.audit = CapabilityAuditService(self.repo_root)

    def evaluate(self, path: str) -> RetrievalGuardDecision:
        normalized = self._normalize(path)
        if normalized is None:
            return RetrievalGuardDecision(False, "path_must_be_repo_relative")
        for pattern in self.deny_patterns:
            if self._matches(normalized, pattern):
                return RetrievalGuardDecision(False, "retrieval_path_denylisted", {"pattern": pattern, "path": normalized})
        if any(normalized.lower().endswith(suffix) for suffix in self.GENERATED_SUFFIXES):
            return RetrievalGuardDecision(False, "generated_or_binary_suffix_denied", {"path": normalized})
        full = self.repo_root / normalized
        if not full.is_file():
            return RetrievalGuardDecision(False, "retrieval_path_not_file", {"path": normalized})
        if full.suffix.lower() not in self.TEXT_SUFFIXES:
            return RetrievalGuardDecision(False, "retrieval_suffix_not_supported", {"path": normalized, "suffix": full.suffix.lower()})
        return RetrievalGuardDecision(True, "retrieval_allowed", {"path": normalized})

    def is_retrievable(self, path: str, *, requester_identity: dict[str, Any] | None = None, audit_denial: bool = True) -> bool:
        decision = self.evaluate(path)
        if not decision.allowed and audit_denial:
            self.audit_denial(path, decision, requester_identity=requester_identity)
        return decision.allowed

    def audit_denial(self, path: str, decision: RetrievalGuardDecision, *, requester_identity: dict[str, Any] | None = None) -> None:
        requester = requester_identity or {}
        self.audit.record(CapabilityAuditRecord(
            session_id=str(requester.get("session_id") or ""),
            agent_id=str(requester.get("agent_id") or ""),
            capability_id="evidence.request",
            success=False,
            reason="evidence_retrieval_denied",
            client_id=str(requester.get("client_id")) if requester.get("client_id") else None,
            project_id=str(requester.get("project_id")) if requester.get("project_id") else None,
            participant_id=str(requester.get("participant_id")) if requester.get("participant_id") else None,
            metadata={"path": path, "denial_reason": decision.reason, **decision.metadata},
        ))

    def _normalize(self, path: str) -> str | None:
        relative = Path(str(path))
        if relative.is_absolute() or ".." in relative.parts:
            return None
        normalized = relative.as_posix()
        if normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    def _matches(self, path: str, pattern: str) -> bool:
        clean = pattern.replace("\\", "/").strip().lstrip("./")
        if not clean:
            return False
        return path == clean or fnmatch.fnmatch(path, clean) or path.startswith(clean.rstrip("/**") + "/")
