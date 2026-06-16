from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RepairControls:
    max_local_attempts: int = 3
    allow_cloud_escalation: bool = True
    max_cloud_attempts: int = 1


@dataclass(frozen=True)
class CloudControls:
    max_context_tokens: int = 6000
    max_evidence_items: int = 8
    max_failure_summary_chars: int = 4000
    allow_full_logs: bool = False
    allow_full_file_contents: bool = False


@dataclass(frozen=True)
class ValidationControls:
    require_validation: bool = True
    allow_validation_bypass: bool = False


@dataclass(frozen=True)
class GovernanceControls:
    require_human_review: bool = True
    allow_auto_promotion: bool = False
    allow_auto_commit: bool = False
    allow_direct_repo_modification: bool = False


@dataclass(frozen=True)
class PromotionConfidenceControls:
    enabled: bool = True
    minimum_confidence: float = 0.80
    ratings: dict[str, float] | None = None
    weights: dict[str, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ratings", self.ratings or {"high": 0.90, "medium": 0.75, "low": 0.50})
        object.__setattr__(self, "weights", self.weights or {
            "proposal_quality": 0.20,
            "requirement_traceability": 0.20,
            "behavioral_verification": 0.20,
            "validation_evidence": 0.20,
            "runtime_execution": 0.20,
        })




@dataclass(frozen=True)
class PromotionGovernanceControls:
    enabled: bool = True
    human_approval_required: bool = True
    minimum_confidence: float = 0.80
    allow_promotion_with_blockers: bool = False


class ControlsService:
    """
    Centralized configuration service for Ageix governance and controls.

    Loads controls.json, applies defaults, and enforces governance
    safety boundaries.
    """

    DEFAULT_CONFIG = {
        "version": 1,
        "repair": {
            "max_local_attempts": 3,
            "allow_cloud_escalation": True,
            "max_cloud_attempts": 1,
        },
        "cloud": {
            "max_context_tokens": 6000,
            "max_evidence_items": 8,
            "max_failure_summary_chars": 4000,
            "allow_full_logs": False,
            "allow_full_file_contents": False,
        },
        "validation": {
            "require_validation": True,
            "allow_validation_bypass": False,
        },
        "governance": {
            "require_human_review": True,
            "allow_auto_promotion": False,
            "allow_auto_commit": False,
            "allow_direct_repo_modification": False,
        },
        "promotion_confidence": {
            "enabled": True,
            "minimum_confidence": 0.80,
            "ratings": {
                "high": 0.90,
                "medium": 0.75,
                "low": 0.50,
            },
            "weights": {
                "proposal_quality": 0.20,
                "requirement_traceability": 0.20,
                "behavioral_verification": 0.20,
                "validation_evidence": 0.20,
                "runtime_execution": 0.20,
            },
        },
        "promotion_governance": {
            "enabled": True,
            "human_approval_required": True,
            "minimum_confidence": 0.80,
            "allow_promotion_with_blockers": False,
        },
        "dependency_intelligence": {
            "enabled": True,
            "max_depth": 2,
            "max_nodes": 50,
            "max_imports_per_file": 25,
            "follow_test_imports": True,
            "follow_runtime_imports": True,
            "allow_proposed_local_imports": True,
            "allow_existing_local_imports": True,
            "allow_stdlib_imports": True,
            "allowed_test_dependencies": ["pytest"],
            "blocked_dependencies": [],
            "unknown_dependency_policy": "fail",
        },
        "repository_impact": {
            "enabled": True,
            "max_depth": 2,
            "max_nodes": 75,
            "max_dependents_per_file": 25,
            "retry_on_limit": True,
            "retry_max_depth": 4,
            "retry_max_nodes": 200,
            "retry_max_dependents_per_file": 75,
            "retry_policy": "validation_failure_only",
            "include_tests": True,
            "include_runtime_files": True,
            "include_companion_tests": True,
            "impacted_test_depth": 1,
            "auto_add_companion_tests": True,
            "auto_add_impacted_tests": True,
            "recommend_indirect_dependents": True,
            "circular_dependency_policy": "warn_stop_path",
            "unresolved_import_policy": "warn",
            "unknown_impact_policy": "warn",
            "limit_policy": "warn",
            "exclude_paths": [
                ".git/",
                ".pytest_cache/",
                ".mypy_cache/",
                ".ruff_cache/",
                "__pycache__/",
                "venv/",
                ".venv/",
                "env/",
                ".env/",
                "site-packages/",
                "node_modules/",
                "build/",
                "dist/",
                "*.egg-info/",
                "artifacts/",
                "htmlcov/",
                ".tox/",
                ".ageix/staged/",
                ".ageix/staging/",
                ".ageix/manifests/",
                ".ageix/runs/",
                ".ageix/runtime/",
                ".ageix/verification/",
                ".ageix/repair_loops/",
                ".ageix/logs/"
            ],
        },
        "cloud_context": {
            "include_impact_summary": True,
            "include_full_impact_evidence": False,
            "max_impact_items": 10,
        },
        "evidence_context": {
            "mode": "target_scoped",
            "include_full_repo_inventory": False,
            "include_target_files": True,
            "include_impacted_files": True,
            "include_impacted_tests": True,
            "include_dependency_neighbors": True,
            "max_files": 20,
            "max_chars": 30000,
            "overflow_policy": "summarize",
            "code_context_mode": "sliced",
            "allow_full_file_fallback": True,
            "max_slice_lines_per_file": 120,
            "include_imports": True,
            "include_adjacent_helpers": True,
        },
    }

    def __init__(self, repo_root: Path):
        self._repo_root = Path(repo_root)

        self._config = self._load_config()

        self.repair = RepairControls(**self._config["repair"])
        self.cloud = CloudControls(**self._config["cloud"])
        self.validation = ValidationControls(**self._config["validation"])
        self.governance = GovernanceControls(**self._config["governance"])
        self.promotion_confidence = PromotionConfidenceControls(**self._config["promotion_confidence"])
        self.promotion_governance = PromotionGovernanceControls(**self._config["promotion_governance"])

    def _load_config(self) -> dict[str, Any]:
        config_path = (
            self._repo_root
            / ".ageix"
            / "config"
            / "controls.json"
        )

        merged = deepcopy(self.DEFAULT_CONFIG)

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as handle:
                    user_config = json.load(handle)

                if isinstance(user_config, dict):
                    self._deep_merge(merged, user_config)

            except Exception:
                pass

        self._apply_governance_clamps(merged)

        return merged

    def _deep_merge(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:
        for key, value in source.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(target[key], value)
            else:
                target[key] = value

    def _apply_governance_clamps(
        self,
        config: dict[str, Any],
    ) -> None:
        governance = config.setdefault("governance", {})
        validation = config.setdefault("validation", {})
        promotion_governance = config.setdefault("promotion_governance", {})

        governance["allow_auto_promotion"] = False
        governance["allow_auto_commit"] = False
        governance["allow_direct_repo_modification"] = False

        validation["allow_validation_bypass"] = False
        promotion_governance["allow_promotion_with_blockers"] = False

    def get_raw_config(self) -> dict[str, Any]:
        return deepcopy(self._config)