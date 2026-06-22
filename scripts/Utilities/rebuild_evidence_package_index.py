from __future__ import annotations

import json
from pathlib import Path

from services.evidence_package_index_service import EvidencePackageIndexService


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    service = EvidencePackageIndexService(repo)
    result = service.rebuild_from_package_store()
    validation = service.validate_index()
    print(json.dumps({"rebuild": result, "validation": validation}, indent=2, sort_keys=True))
    return 0 if validation["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
