#!/usr/bin/env python3
"""Run the task-bound V3-MIG-002 rollback rehearsal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tcfactory.v3.rollback_rehearsal import RollbackAttestationError, rehearse  # noqa: E402

ATTESTATION = ROOT / "docs/migrations/V3_MIG_002_ROLLBACK_ATTESTATION.json"


def main() -> int:
    try:
        result = rehearse(ROOT, ATTESTATION)
    except (OSError, ValueError, RollbackAttestationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
