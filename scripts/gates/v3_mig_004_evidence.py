#!/usr/bin/env python3
"""Generate deterministic, non-authoritative evidence for V3-MIG-004."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/migrations/evidence/V3-MIG-004.json"
BOUND_FILES = (
    "config/source_precedence.yaml",
    "SOURCE_PRECEDENCE.md",
    "scripts/gates/source_of_truth_integrity.py",
    "tests/test_v3_mig_004_source_precedence.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_evidence(root: Path = ROOT) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "taskId": "V3-MIG-004",
        "claim": "Source precedence and context authority are executable and fail closed.",
        "localVerificationState": "VERIFIED",
        "independentAuthorityState": "MISSING_NOT_REQUIRED_FOR_LOCAL_ENGINEERING_EVIDENCE",
        "independentAuthorityReceipt": None,
        "limitations": [
            "This artifact is deterministic repository evidence, not an independent review.",
            "It does not authorize publication, activation, or a completion-ledger transition.",
        ],
        "bindings": [
            {"path": relative, "sha256": _sha256(root / relative)}
            for relative in BOUND_FILES
        ],
        "verification": {
            "command": [
                ".venv/bin/python",
                "-m",
                "pytest",
                "-q",
                "tests/test_v3_mig_004_source_precedence.py",
                "tests/test_source_of_truth_integrity.py",
            ],
            "negativeCases": [
                "precedence mutation with recomputed self-digest",
                "missing precedence source",
                "duplicate precedence source",
                "missing manifest source",
                "normative source in current-fact group",
                "current fact in normative group",
                "role/group authority mismatch",
                "stale current fact",
                "duplicate context entry",
            ],
        },
    }


def render(root: Path = ROOT) -> str:
    return json.dumps(build_evidence(root), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print(f"FAIL: stale or missing deterministic evidence: {OUTPUT}")
            return 1
        print("PASS: V3-MIG-004 deterministic evidence is current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
