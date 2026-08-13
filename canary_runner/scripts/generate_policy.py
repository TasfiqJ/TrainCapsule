#!/usr/bin/env python3
"""Generate a root-installer template with all 20 explicit mechanism targets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from traincapsule_canary_runner.models import MandatoryCanaryId

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "policy/runner-policy.template.json"
NETWORK = {
    MandatoryCanaryId.REAL_CLAUDE_MECHANICAL_TASK,
    MandatoryCanaryId.POST_MERGE_INVARIANT_FAILURE_AND_AUTOMATED_REVERT_PR,
}


def rendered() -> bytes:
    placeholder = "sha256:" + "0" * 64
    payload = {
        "schemaVersion": "3.1",
        "runnerExecutableDigest": placeholder,
        "distributionDigest": placeholder,
        "mechanisms": {
            item.value: {
                "executable": f"/usr/libexec/traincapsule-canary-{item.value}",
                "executableDigest": placeholder,
                "timeoutSeconds": 3600 if item in NETWORK else 300,
                "networkAllowed": item in NETWORK,
            }
            for item in MandatoryCanaryId
        },
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = rendered()
    if args.check:
        if not TARGET.is_file() or TARGET.read_bytes() != content:
            raise SystemExit("canary runner policy template is stale")
        print("PASS: exact 20-mechanism runner policy template")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(content)
    print(f"Wrote {TARGET}; template digest sha256:{hashlib.sha256(content).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
