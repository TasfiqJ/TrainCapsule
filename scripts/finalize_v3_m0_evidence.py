#!/usr/bin/env python3
"""Historical V3 finalizer retained as a fail-closed compatibility tombstone."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "BLOCKED_POLICY: historical V3 local/simulation evidence cannot finalize "
        "V3.1 M0; use scripts/finalize_v3_1_zh_m0_evidence.py after independent "
        "signed authorization and real automated-PR/required-CI/merged-main receipts exist",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
