#!/usr/bin/env python3
"""Verify the deterministic historical evidence binding for V3-MIG-001."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.mig_001_reverification import (  # noqa: E402
    EVIDENCE_PATH,
    Mig001ReverificationError,
    render_reverification,
    validate_reverification,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        if args.write:
            path = repo_root / EVIDENCE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(render_reverification(repo_root))
        evidence = validate_reverification(repo_root)
    except (OSError, ValueError, Mig001ReverificationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS: V3-MIG-001 historical baseline, clean status, queue, and "
        f"checkpoint evidence are bound by {evidence['evidenceDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
