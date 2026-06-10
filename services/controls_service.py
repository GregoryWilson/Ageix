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
    }

    def __init__(self, repo_root: Path):
        self._repo_root = Path(repo_root)

        self._config = self._load_config()

        self.repair = RepairControls(**self._config["repair"])
        self.cloud = CloudControls(**self._config["cloud"])
        self.validation = ValidationControls(**self._config["validation"])
        self.governance = GovernanceControls(**self._config["governance"])

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

        governance["allow_auto_promotion"] = False
        governance["allow_auto_commit"] = False
        governance["allow_direct_repo_modification"] = False

        validation["allow_validation_bypass"] = False

    def get_raw_config(self) -> dict[str, Any]:
        return deepcopy(self._config)