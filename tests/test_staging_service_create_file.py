import pytest

from services.staging_service import StagingService


def build_proposal(operation: str, path: str, content: str = "hello = 'world'\n") -> dict:
    return {
        "result_type": "patch_proposal",
        "objective": "Test staging create_file behavior",
        "summary": "Test patch proposal",
        "files_considered": [path],
        "evidence_used": [],
        "dependency_hints_used": [],
        "assumptions": [],
        "dependency_risks": [],
        "changes": [
            {
                "operation": operation,
                "path": path,
                "content": content,
            }
        ],
        "test_plan": ["pytest"],
        "no_write_confirmation": True,
    }


def test_create_file_missing_file_stages_successfully(tmp_path):
    service = StagingService(tmp_path)

    proposal = build_proposal(
        operation="create_file",
        path="services/new_service.py",
        content="def hello():\n    return 'world'\n",
    )

    manifest = service.create_stage_from_patch_proposal(proposal)

    staged_file = (
        tmp_path
        / ".ageix"
        / "staged"
        / manifest.patch_id
        / "files"
        / "services"
        / "new_service.py"
    )

    assert staged_file.exists()
    assert staged_file.read_text(encoding="utf-8") == "def hello():\n    return 'world'\n"

    manifest_file = manifest.files[0]
    assert manifest_file.path == "services/new_service.py"
    assert manifest_file.operation == "create"
    assert manifest_file.original_hash is None
    assert manifest_file.staged_hash is not None


def test_create_file_existing_file_is_rejected(tmp_path):
    existing_file = tmp_path / "services" / "existing_service.py"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text("def existing():\n    return True\n", encoding="utf-8")

    service = StagingService(tmp_path)

    proposal = build_proposal(
        operation="create_file",
        path="services/existing_service.py",
        content="def replacement():\n    return False\n",
    )

    with pytest.raises(ValueError, match="create_file cannot overwrite existing file"):
        service.create_stage_from_patch_proposal(proposal)


def test_replace_file_existing_file_stages_successfully(tmp_path):
    existing_file = tmp_path / "services" / "existing_service.py"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text("def existing():\n    return True\n", encoding="utf-8")

    service = StagingService(tmp_path)

    proposal = build_proposal(
        operation="replace_file",
        path="services/existing_service.py",
        content="def existing():\n    return False\n",
    )

    manifest = service.create_stage_from_patch_proposal(proposal)

    staged_file = (
        tmp_path
        / ".ageix"
        / "staged"
        / manifest.patch_id
        / "files"
        / "services"
        / "existing_service.py"
    )

    assert staged_file.exists()
    assert staged_file.read_text(encoding="utf-8") == "def existing():\n    return False\n"

    manifest_file = manifest.files[0]
    assert manifest_file.path == "services/existing_service.py"
    assert manifest_file.operation == "modify"
    assert manifest_file.original_hash is not None
    assert manifest_file.staged_hash is not None


def test_replace_file_missing_file_is_rejected(tmp_path):
    service = StagingService(tmp_path)

    proposal = build_proposal(
        operation="replace_file",
        path="services/missing_service.py",
        content="def missing():\n    return True\n",
    )

    with pytest.raises(ValueError, match="replace_file requires existing file"):
        service.create_stage_from_patch_proposal(proposal)