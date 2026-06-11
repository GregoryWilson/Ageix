from services.objective_source_service import (
    DEFAULT_OBJECTIVE,
    ObjectiveSourceService,
)


def test_direct_text_objective_wins_over_file(tmp_path):
    objective_file = tmp_path / ".ageix" / "objectives" / "current_objective.txt"
    objective_file.parent.mkdir(parents=True)
    objective_file.write_text("File objective", encoding="utf-8")

    service = ObjectiveSourceService(repo_root=tmp_path)

    envelope = service.resolve_objective(
        objective_text="CLI objective",
        objective_file=objective_file,
    )

    assert envelope["title"] == "CLI objective"
    assert envelope["description"] == "CLI objective"
    assert envelope["source"] == "cli"


def test_objective_file_loads_when_no_direct_text(tmp_path):
    objective_file = tmp_path / ".ageix" / "objectives" / "current_objective.txt"
    objective_file.parent.mkdir(parents=True)
    objective_file.write_text(
        "File objective\nWith more detail",
        encoding="utf-8",
    )

    service = ObjectiveSourceService(repo_root=tmp_path)

    envelope = service.resolve_objective(objective_file=objective_file)

    assert envelope["title"] == "File objective"
    assert envelope["description"] == "File objective\nWith more detail"
    assert envelope["source"] == "file"
    assert envelope["metadata"]["path"] == str(objective_file)


def test_missing_objective_file_falls_back_to_default(tmp_path):
    service = ObjectiveSourceService(repo_root=tmp_path)

    envelope = service.resolve_objective(
        objective_file=tmp_path / "missing.txt",
    )

    assert envelope["title"] == DEFAULT_OBJECTIVE
    assert envelope["description"] == DEFAULT_OBJECTIVE
    assert envelope["source"] == "default"


def test_empty_objective_file_falls_back_to_default(tmp_path):
    objective_file = tmp_path / "empty.txt"
    objective_file.write_text("   \n", encoding="utf-8")

    service = ObjectiveSourceService(repo_root=tmp_path)

    envelope = service.resolve_objective(objective_file=objective_file)

    assert envelope["title"] == DEFAULT_OBJECTIVE
    assert envelope["source"] == "default"


def test_default_relative_objective_file_is_loaded_from_repo_root(tmp_path):
    objective_file = tmp_path / ".ageix" / "objectives" / "current_objective.txt"
    objective_file.parent.mkdir(parents=True)
    objective_file.write_text("Default file objective", encoding="utf-8")

    service = ObjectiveSourceService(repo_root=tmp_path)

    envelope = service.resolve_objective()

    assert envelope["title"] == "Default file objective"
    assert envelope["source"] == "file"


def test_envelope_structure_is_deterministic():
    service = ObjectiveSourceService()

    first = service.resolve_objective(objective_text="Same objective")
    second = service.resolve_objective(objective_text="Same objective")

    assert first == second
    assert set(first.keys()) == {
        "objective_id",
        "title",
        "description",
        "project_id",
        "source",
        "priority",
        "tags",
        "metadata",
    }