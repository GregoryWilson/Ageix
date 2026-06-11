import json
from pathlib import Path

import pytest

from services.project_profile_service import ProjectProfileService
from services.project_registry_service import ProjectRegistryError


def test_one_project_creates_registry_and_profile(tmp_path: Path):
    root = tmp_path / "ageix"
    target = tmp_path / "target"

    service = ProjectProfileService(root)
    project = service.register_project(
        project_id="project_alpha",
        name="Project Alpha",
        project_type="python",
        root_path=target,
        metadata={"owner": "test"},
    )

    registry_path = root / ".ageix" / "instance" / "workspace_registry.json"
    profile_path = root / ".ageix" / "projects" / "project_alpha" / "project_profile.json"

    assert registry_path.exists()
    assert profile_path.exists()

    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    assert profile["project_id"] == "project_alpha"
    assert profile["name"] == "Project Alpha"
    assert profile["project_type"] == "python"
    assert profile["root_path"] == str(target.resolve())
    assert profile["brain_path"] == project["brain_path"]
    assert profile["project_role"] == "target"
    assert profile["status"] == "active"
    assert profile["metadata"] == {"owner": "test"}


def test_two_project_profiles_coexist_independently(tmp_path: Path):
    root = tmp_path / "ageix"

    service = ProjectProfileService(root)
    first = service.register_project("project_one", "One", "python", tmp_path / "one")
    second = service.register_project("project_two", "Two", "node", tmp_path / "two")

    first_profile_path = Path(first["brain_path"]) / "project_profile.json"
    second_profile_path = Path(second["brain_path"]) / "project_profile.json"

    assert first_profile_path.exists()
    assert second_profile_path.exists()
    assert first_profile_path != second_profile_path

    first_profile = json.loads(first_profile_path.read_text(encoding="utf-8"))
    second_profile = json.loads(second_profile_path.read_text(encoding="utf-8"))

    assert first_profile["project_id"] == "project_one"
    assert second_profile["project_id"] == "project_two"
    assert first_profile["root_path"] != second_profile["root_path"]


def test_duplicate_project_id_rejected_before_profile_overwrite(tmp_path: Path):
    service = ProjectProfileService(tmp_path / "ageix")

    first = service.register_project("project_dup", "Dup", "python", tmp_path / "target")
    profile_path = Path(first["brain_path"]) / "project_profile.json"
    original_profile = profile_path.read_text(encoding="utf-8")

    with pytest.raises(ProjectRegistryError, match="already registered"):
        service.register_project("project_dup", "Dup Again", "python", tmp_path / "other")

    assert profile_path.read_text(encoding="utf-8") == original_profile


def test_profile_service_resolve_project_returns_root_and_brain_path(tmp_path: Path):
    root = tmp_path / "ageix"
    target = tmp_path / "target"

    service = ProjectProfileService(root)
    service.register_project("project_resolve", "Resolve", "python", target)

    resolved = service.resolve_project("project_resolve")

    assert resolved["project_id"] == "project_resolve"
    assert resolved["root_path"] == str(target.resolve())
    assert resolved["brain_path"] == str((root / ".ageix" / "projects" / "project_resolve").resolve())


def test_profile_service_registry_survives_reload(tmp_path: Path):
    root = tmp_path / "ageix"

    service = ProjectProfileService(root)
    service.register_project("project_reload", "Reload", "python", tmp_path / "target")

    reloaded = ProjectProfileService(root)
    project = reloaded.get_project("project_reload")

    assert project["project_id"] == "project_reload"
    assert project["name"] == "Reload"


def test_invalid_project_id_does_not_create_profile(tmp_path: Path):
    root = tmp_path / "ageix"
    service = ProjectProfileService(root)

    with pytest.raises(ProjectRegistryError, match="Invalid project_id"):
        service.register_project("../bad", "Bad", "python", tmp_path / "target")

    assert not (root / ".ageix" / "projects").exists()