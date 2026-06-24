from __future__ import annotations

from pprint import pprint

from services.ageix_architecture_baseline_service import AgeixArchitectureBaselineService


def main() -> None:
    print("== Smoke 18.10: Ageix canonical architecture baseline ==")
    service = AgeixArchitectureBaselineService(".")
    populated = service.populate(include_review=True)
    validation = service.validate()
    probe = service.retrieval_probe()
    summary = {
        "baseline_version": populated["baseline_version"],
        "total_node_count": populated["total_node_count"],
        "domain_count": populated["domain_count"],
        "component_count": populated["component_count"],
        "service_count": populated["service_count"],
        "principle_count": populated["principle_count"],
        "intent_count": populated["intent_count"],
        "adr_count": populated["adr_count"],
        "valid": validation["valid"],
        "retrieval_usable": probe["retrieval_usable"],
        "review_id": populated.get("review_id"),
    }
    pprint(summary)
    assert validation["valid"] is True
    assert probe["retrieval_usable"] is True
    assert populated["service_count"] >= 45
    print("Smoke 18.10 PASS: Ageix canonical architecture baseline populated, validated, reviewed cautiously, and retrievable.")


if __name__ == "__main__":
    main()
