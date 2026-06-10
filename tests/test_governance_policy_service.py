import json
from pathlib import Path

from services.governance_policy_service import GovernancePolicyService


def test_governance_policy_uses_controls_for_tunable_repair_limits(tmp_path: Path):
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)

    (config_dir / "controls.json").write_text(
        json.dumps(
            {
                "repair": {
                    "max_local_attempts": 5,
                    "allow_cloud_escalation": False,
                }
            }
        ),
        encoding="utf-8",
    )

    svc = GovernancePolicyService(tmp_path)

    assert svc.maximum_local_repair_attempts() == 5
    assert svc.may_escalate_to_cloud() is False


def test_governance_policy_enforces_locked_safety_boundaries(tmp_path: Path):
    config_dir = tmp_path / ".ageix" / "config"
    config_dir.mkdir(parents=True)

    (config_dir / "controls.json").write_text(
        json.dumps(
            {
                "validation": {
                    "require_validation": False,
                    "allow_validation_bypass": True,
                },
                "governance": {
                    "require_human_review": False,
                    "allow_auto_promotion": True,
                    "allow_auto_commit": True,
                    "allow_direct_repo_modification": True,
                },
            }
        ),
        encoding="utf-8",
    )

    svc = GovernancePolicyService(tmp_path)

    assert svc.must_request_human_review() is True
    assert svc.must_validate_patch() is True
    assert svc.may_bypass_validation() is False
    assert svc.may_promote_patch() is False
    assert svc.may_commit_patch() is False
    assert svc.may_modify_live_repository() is False