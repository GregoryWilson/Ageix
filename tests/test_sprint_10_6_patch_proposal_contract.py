from agents.dev_worker_agent import normalize_devworker_result
from chair import normalize_patch_proposal_deliverable, validate_patch_proposal_deliverable
from services.patch_proposal_contract_service import PatchProposalContractService


def _base_proposal(**overrides):
    proposal = {
        "result_type": "patch_proposal",
        "objective": "Create utility",
        "summary": "Create utility",
        "files_considered": ["utils/example.py"],
        "evidence_used": [],
        "dependency_hints_used": [],
        "assumptions": [],
        "dependency_risks": [],
        "changes": [
            {
                "path": "utils/example.py",
                "operation": "create_file",
                "content": "def example():\n    return True\n",
            }
        ],
        "test_plan": ["PYTHONPATH=. python -m pytest"],
        "no_write_confirmation": True,
    }
    proposal.update(overrides)
    return proposal


def test_changes_contract_passes():
    proposal = _base_proposal()

    normalized = normalize_patch_proposal_deliverable(proposal)
    validate_patch_proposal_deliverable(normalized)

    assert normalized["changes"]
    assert "patch_proposal_normalization_evidence" in normalized


def test_proposed_changes_normalizes_to_changes():
    proposal = _base_proposal()
    proposal["proposed_changes"] = proposal.pop("changes")

    normalized = normalize_patch_proposal_deliverable(proposal)

    assert normalized["changes"] == proposal["proposed_changes"]
    assert normalized["patch_proposal_normalization_evidence"]["normalized_from"]["changes"] == "proposed_changes"
    validate_patch_proposal_deliverable(normalized)


def test_empty_changes_fails_after_normalization():
    proposal = _base_proposal(changes=[])

    normalized = normalize_patch_proposal_deliverable(proposal)

    try:
        validate_patch_proposal_deliverable(normalized)
    except ValueError as ex:
        assert "Patch proposal must include at least one change" in str(ex)
    else:
        raise AssertionError("Expected empty changes to fail")


def test_missing_change_operation_fails():
    proposal = _base_proposal(
        changes=[{"path": "utils/example.py", "content": "x = 1\n"}]
    )

    normalized = normalize_patch_proposal_deliverable(proposal)

    try:
        validate_patch_proposal_deliverable(normalized)
    except ValueError as ex:
        assert "Unsupported patch proposal operation" in str(ex)
    else:
        raise AssertionError("Expected missing operation to fail")


def test_missing_change_path_fails():
    proposal = _base_proposal(
        changes=[{"operation": "create_file", "content": "x = 1\n"}]
    )

    normalized = normalize_patch_proposal_deliverable(proposal)

    try:
        validate_patch_proposal_deliverable(normalized)
    except ValueError as ex:
        assert "Patch proposal change missing path" in str(ex)
    else:
        raise AssertionError("Expected missing path to fail")


def test_changes_win_when_proposed_changes_empty():
    proposal = _base_proposal(proposed_changes=[])

    normalized = normalize_patch_proposal_deliverable(proposal)

    assert normalized["changes"] == proposal["changes"]
    assert normalized["proposed_changes"] == proposal["changes"]
    validate_patch_proposal_deliverable(normalized)


def test_normalization_evidence_records_missing_fields():
    proposal = _base_proposal()
    proposal["proposed_changes"] = proposal.pop("changes")

    normalized, evidence = PatchProposalContractService().normalize(proposal)

    assert "changes" in evidence.missing_fields_before_normalization
    assert "changes" not in evidence.missing_fields_after_normalization
    assert normalized["patch_proposal_normalization_evidence"] == evidence.model_dump()


def test_devworker_normalization_preserves_canonical_changes():
    packet = {"objective": "Create utility"}
    proposal = _base_proposal(proposed_changes=[])

    normalized = normalize_devworker_result(proposal, packet)

    assert normalized["changes"] == proposal["changes"]
    assert normalized["proposed_changes"] == proposal["changes"]
    assert "patch_proposal_normalization_evidence" in normalized
