from pathlib import Path

from services.controls_service import ControlsService


def test_missing_config_uses_defaults(tmp_path: Path):
    svc = ControlsService(tmp_path)

    assert svc.repair.max_local_attempts == 3
    assert svc.cloud.max_context_tokens == 6000
    assert svc.governance.require_human_review is True


def test_partial_config_merges_defaults(tmp_path: Path):
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)

    (config_dir / "controls.json").write_text(
        """
        {
            "repair": {
                "max_local_attempts": 5
            }
        }
        """,
        encoding="utf-8",
    )

    svc = ControlsService(tmp_path)

    assert svc.repair.max_local_attempts == 5
    assert svc.cloud.max_context_tokens == 6000


def test_governance_clamps_are_enforced(tmp_path: Path):
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)

    (config_dir / "controls.json").write_text(
        """
        {
            "governance": {
                "allow_auto_commit": true,
                "allow_auto_promotion": true
            }
        }
        """,
        encoding="utf-8",
    )

    svc = ControlsService(tmp_path)

    assert svc.governance.allow_auto_commit is False
    assert svc.governance.allow_auto_promotion is False