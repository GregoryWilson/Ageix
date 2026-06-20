from pathlib import Path
import subprocess

from services.test_execution_service import TestExecutionService


def write_repo(tmp_path: Path, test_body: str = "def test_sample():\n    assert True\n") -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_runtime_sample.py").write_text(test_body, encoding="utf-8")


def patch_run(monkeypatch, *, returncode: int, stdout: str = "", stderr: str = ""):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_execution_service_runs_passing_test(tmp_path: Path, monkeypatch):
    write_repo(tmp_path)
    patch_run(monkeypatch, returncode=0, stdout="1 passed")

    result = TestExecutionService(tmp_path).execute(["tests/test_runtime_sample.py::test_sample"])

    assert result.passed
    assert result.runtime_evidence[0].status == "passed"
    assert result.runtime_evidence[0].duration_seconds >= 0


def test_execution_service_reports_failure(tmp_path: Path, monkeypatch):
    write_repo(tmp_path)
    patch_run(monkeypatch, returncode=1, stdout="1 failed")

    result = TestExecutionService(tmp_path).execute(["tests/test_runtime_sample.py::test_sample"])

    assert not result.passed
    assert result.violations[0].code == "TEST_EXECUTION_FAILED"


def test_execution_service_reports_missing_test(tmp_path: Path, monkeypatch):
    write_repo(tmp_path)
    patch_run(monkeypatch, returncode=4, stderr="ERROR: not found: tests/test_runtime_sample.py::test_missing")

    result = TestExecutionService(tmp_path).execute(["tests/test_runtime_sample.py::test_missing"])

    assert not result.passed
    assert result.violations[0].code == "TEST_NOT_FOUND"


def test_execution_service_handles_timeout(tmp_path: Path, monkeypatch):
    write_repo(tmp_path)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    result = TestExecutionService(tmp_path, timeout_seconds=0.1).execute(
        ["tests/test_runtime_sample.py::test_sample"]
    )

    assert not result.passed
    assert result.violations[0].code == "TEST_TIMEOUT"


def test_execution_service_applies_proposal_overlay(tmp_path: Path):
    proposal = {
        "changes": [
            {
                "operation": "create_file",
                "path": "services/runtime_sample.py",
                "content": "def message():\n    return 'observed'\n",
            },
            {
                "operation": "create_file",
                "path": "tests/test_runtime_overlay.py",
                "content": "from services.runtime_sample import message\n\ndef test_runtime_overlay():\n    assert message() == 'observed'\n",
            },
        ]
    }

    service = TestExecutionService(tmp_path)
    with service._execution_workspace(proposal) as workspace:
        assert (workspace / "services" / "runtime_sample.py").exists()
        assert (workspace / "tests" / "test_runtime_overlay.py").exists()
