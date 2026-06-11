import json
from pathlib import Path

import pytest

from services.project_registry_service import ProjectRegistryError, ProjectRegistryService


def test_one_project_creates_registry(tmp_path: Path):
    root = tmp_path / "ageix"
    target = tmp_path / "target"

    service = ProjectRegistryService(root)
    project = service.register_project(
        project_id="project_alpha",
        name="Project Alpha",
        project_type="python",
        root_path=target,
    )

    registry_path = root / ".ageix" / "instance" / "workspace_registry.json"

    assert registry_path.exists()
    assert project["project_id"] == "project_alpha"
    assert project["root_path"] == str(target.resolve())
    assert project["brain_path"] == str((root / ".ageix" / "projects" / "project_alpha").resolve())

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "project_alpha" in data["projects"]


def test_two_projects_coexist_independently(tmp_path: Path):
    root = tmp_path / "ageix"

    service = ProjectRegistryService(root)
    first = service.register_project("project_one", "One", "python", tmp_path / "one")
    second = service.register_project("project_two", "Two", "node", tmp_path / "two")

    projects = service.list_projects()

    assert len(projects) == 2
    assert first["project_id"] != second["project_id"]
    assert first["root_path"] != second["root_path"]
    assert first["brain_path"] != second["brain_path"]


def test_duplicate_project_id_is_rejected(tmp_path: Path):
    service = ProjectRegistryService(tmp_path / "ageix")

    service.register_project("project_dup", "Dup", "python", tmp_path / "target")

    with pytest.raises(ProjectRegistryError, match="already registered"):
        service.register_project("project_dup", "Dup Again", "python", tmp_path / "other")


def test_resolve_project_returns_root_and_brain_path(tmp_path: Path):
    root = tmp_path / "ageix"
    target = tmp_path / "target"

    service = ProjectRegistryService(root)
    service.register_project("project_resolve", "Resolve", "python", target)

    resolved = service.resolve_project("project_resolve")

    assert resolved == {
        "project_id": "project_resolve",
        "root_path": str(target.resolve()),
        "brain_path": str((root / ".ageix" / "projects" / "project_resolve").resolve()),
    }


def test_registry_survives_service_reload(tmp_path: Path):
    root = tmp_path / "ageix"

    service = ProjectRegistryService(root)
    service.register_project("project_persist", "Persist", "python", tmp_path / "target")

    reloaded = ProjectRegistryService(root)
    project = reloaded.get_project("project_persist")

    assert project["project_id"] == "project_persist"
    assert project["name"] == "Persist"


def test_brain_paths_are_deterministic(tmp_path: Path):
    root = tmp_path / "ageix"

    service = ProjectRegistryService(root)
    first = service.register_project("project_brain", "Brain", "python", tmp_path / "target")

    reloaded = ProjectRegistryService(root)
    resolved = reloaded.resolve_project("project_brain")

    expected = str((root / ".ageix" / "projects" / "project_brain").resolve())

    assert first["brain_path"] == expected
    assert resolved["brain_path"] == expected


@pytest.mark.parametrize(
    "project_id",
    [
        "",
        " ",
        "../escape",
        "bad/id",
        "bad.id",
        "-starts-with-dash",
        "_starts_with_underscore",
        "x" * 65,
    ],
)
def test_invalid_project_ids_fail_cleanly(tmp_path: Path, project_id: str):
    service = ProjectRegistryService(tmp_path / "ageix")

    with pytest.raises(ProjectRegistryError, match="Invalid project_id"):
        service.register_project(project_id, "Bad", "python", tmp_path / "target")