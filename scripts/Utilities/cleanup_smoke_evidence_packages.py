from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.evidence_package_cleanup_service import EvidencePackageCleanupService


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete explicitly marked smoke-demo evidence packages and rebuild the index.")
    parser.add_argument("--dry-run", action="store_true", help="Show packages that would be deleted without deleting them.")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    result = EvidencePackageCleanupService(repo).cleanup_smoke_demo_packages(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["validation_after"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
