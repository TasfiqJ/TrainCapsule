#!/usr/bin/env python3
"""Fail closed unless every M0 receipt is independently replayable and bound."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.migration_evidence import (  # noqa: E402
    MigrationEvidenceError,
    validate_repository_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--prerequisites", action="store_true")
    args = parser.parse_args()
    try:
        count = validate_repository_evidence(
            args.repo_root.resolve(), prerequisites_only=args.prerequisites
        )
    except (OSError, ValueError, subprocess.SubprocessError, MigrationEvidenceError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    scope = "M0 prerequisite" if args.prerequisites else "M0 completion"
    print(f"PASS: {count} {scope} evidence records are exact and independently auditable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
