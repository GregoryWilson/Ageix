from services.behavioral_smoke_verifier import BehavioralSmokeVerifier


def build_proposal(literal):
    return {
        "result_type": "patch_proposal",
        "objective": 'smoke_message returns "create_file smoke passed"',
        "changes": [
            {
                "operation": "create_file",
                "path": "services/smoke_service.py",
                "content": f'def smoke_message():\n    return "{literal}"\n',
            }
        ],
    }


def test_behavioral_smoke_verification_passes_correct_literal():
    result = BehavioralSmokeVerifier().verify(
        proposal=build_proposal("create_file smoke passed"),
        objective='smoke_message returns "create_file smoke passed"',
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert result.passed
    assert result.checks


def test_behavioral_smoke_verification_rejects_incorrect_literal():
    result = BehavioralSmokeVerifier().verify(
        proposal=build_proposal("Smoke test successful!"),
        objective='smoke_message returns "create_file smoke passed"',
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert not result.passed
    violation = result.violations[0]
    assert violation.code == "REQUIRED_LITERAL_MISSING"
    assert violation.expected == "create_file smoke passed"
    assert violation.actual == "Smoke test successful!"
    assert violation.instruction == "Preserve requested literal exactly."


def test_behavioral_smoke_verification_rejects_missing_function_name():
    result = BehavioralSmokeVerifier().verify(
        proposal={
            "changes": [
                {
                    "operation": "create_file",
                    "path": "services/smoke_service.py",
                    "content": 'def other_message():\n    return "create_file smoke passed"\n',
                }
            ]
        },
        objective='smoke_message returns "create_file smoke passed"',
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert not result.passed
    assert "REQUIRED_FUNCTION_MISSING" in {violation.code for violation in result.violations}
