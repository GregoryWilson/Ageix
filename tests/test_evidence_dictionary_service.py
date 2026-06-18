from models.work_packet import WorkPacket
from services.evidence_dictionary_service import EvidenceDictionaryService


def test_evidence_dictionary_contains_grounded_scope_only():
    packet = WorkPacket(
        objective="Add consultation governance",
        approved_scope=["services/consultation_proposal_service.py", "tests/test_consultation_proposal_service.py"],
        repository_evidence=["services/controls_service.py"],
        acceptance_criteria=["Requires human approval before cloud spend"],
    )

    dictionary = EvidenceDictionaryService().build_dictionary(packet)

    assert dictionary.excluded_reasons == []
    assert dictionary.items[0].evidence_type == "approved_scope"
    assert dictionary.items[0].requestable is False
    assert "services/consultation_proposal_service.py" in dictionary.items[0].paths
    assert dictionary.estimated_total_tokens > 0


def test_evidence_dictionary_excludes_unresolved_targets():
    packet = WorkPacket(
        objective="Modify hallucinated service",
        approved_scope=["services/real_service.py"],
        unresolved_target_files=["services/not_real.py"],
        planner_revisit_required=True,
    )

    dictionary = EvidenceDictionaryService().build_dictionary(packet)

    assert dictionary.items == []
    assert "unresolved_targets_present" in dictionary.excluded_reasons
    assert dictionary.estimated_total_tokens == 0


def test_evidence_dictionary_summarizes_impact_and_tests():
    packet = WorkPacket(
        objective="Update service",
        approved_scope=["services/foo.py"],
        impacted_files=["services/bar.py"],
        impacted_tests=["tests/test_bar.py"],
        test_targets=["tests/test_foo.py"],
    )

    dictionary = EvidenceDictionaryService().build_dictionary(packet)
    by_type = {item.evidence_type: item for item in dictionary.items}

    assert "impact_summary" in by_type
    assert by_type["impact_summary"].reference_only is True
    assert "tests/test_foo.py" in by_type["test_targets"].paths
