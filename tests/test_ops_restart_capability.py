from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.capability_registry_service import CapabilityRegistryService


def test_restart_daemon_capability_is_registered_and_not_externally_exposed(tmp_path: Path):
    registry = CapabilityRegistryService(tmp_path)
    definition = registry.lookup("ops.restart_daemon")

    assert definition is not None
    assert definition.access_level == "governed_write"
    assert definition.exposed_to_external_agents is False


def test_restart_daemon_errors_when_script_missing(tmp_path: Path):
    handler = CapabilityRegistryService(tmp_path).handler_for("ops.restart_daemon")

    response = handler({})

    assert response["success"] is False
    assert response["error"] == "restart_script_missing_or_not_executable"


def test_restart_daemon_spawns_detached_script_with_env_and_returns_initiated_status(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "scripts" / "Ops" / "restart_ageix.sh"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script_path.chmod(0o755)

    captured: dict[str, Any] = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr("services.capabilities.ops_capabilities.subprocess.Popen", _FakePopen)

    handler = CapabilityRegistryService(tmp_path).handler_for("ops.restart_daemon")
    response = handler({"stop_delay_seconds": 5, "log_file": "/tmp/custom.log"})

    assert response["success"] is True
    assert response["result"]["status"] == "restart_initiated"
    assert response["result"]["stop_delay_seconds"] == 5
    assert response["result"]["log_file"] == "/tmp/custom.log"

    assert captured["args"] == [str(script_path), "restart"]
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["env"]["STOP_DELAY"] == "5"
    assert captured["kwargs"]["env"]["LOG_FILE"] == "/tmp/custom.log"


def test_restart_daemon_uses_defaults_when_no_arguments_given(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "scripts" / "Ops" / "restart_ageix.sh"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script_path.chmod(0o755)

    captured: dict[str, Any] = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr("services.capabilities.ops_capabilities.subprocess.Popen", _FakePopen)

    handler = CapabilityRegistryService(tmp_path).handler_for("ops.restart_daemon")
    response = handler({})

    assert response["success"] is True
    assert response["result"]["stop_delay_seconds"] == 2
    assert response["result"]["log_file"] == "/tmp/ageix_uvicorn.log"
    assert captured["kwargs"]["env"]["STOP_DELAY"] == "2"
