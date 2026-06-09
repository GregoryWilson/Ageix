from __future__ import annotations

from typing import Any


def _section_has_content(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0

    return True


def evaluate_deliverable(
    work_order: dict[str, Any],
    deliverable: dict[str, Any],
) -> dict[str, Any]:
    required_sections = work_order.get("deliverable", {}).get("required_sections", [])
    criteria = work_order.get("success_criteria", [])

    results: list[dict[str, Any]] = []

    if not isinstance(deliverable, dict):
        return {
            "score": 0.0,
            "passed": 0,
            "total": len(required_sections) or len(criteria),
            "results": [
                {
                    "criterion": "Deliverable must be a dictionary",
                    "passed": False,
                    "notes": f"Received {type(deliverable).__name__}.",
                }
            ],
            "missing_sections": required_sections,
        }

    for section in required_sections:
        exists = section in deliverable
        has_content = _section_has_content(deliverable.get(section))

        passed = exists and has_content

        results.append(
            {
                "criterion": f"Required section: {section}",
                "passed": passed,
                "notes": (
                    "Section exists and contains content."
                    if passed
                    else "Section is missing."
                    if not exists
                    else "Section exists but is empty."
                ),
            }
        )

    total = len(results)
    passed_count = sum(1 for result in results if result["passed"])
    score = round((passed_count / total) * 100, 2) if total else None

    missing_sections = [
        section
        for section in required_sections
        if section not in deliverable
    ]

    empty_sections = [
        section
        for section in required_sections
        if section in deliverable and not _section_has_content(deliverable.get(section))
    ]

    return {
        "score": score,
        "passed": passed_count,
        "total": total,
        "results": results,
        "missing_sections": missing_sections,
        "empty_sections": empty_sections,
    }