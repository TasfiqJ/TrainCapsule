"""Minimal local CLI. It cannot post checks, push, merge, or activate runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .attestation import attest_installation, rehearse_layout
from .canonical import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-verifier")
    commands = parser.add_subparsers(dest="command", required=True)
    rehearsal = commands.add_parser("rehearse-install")
    rehearsal.add_argument("--destination", type=Path, required=True)
    rehearsal.add_argument("--public-key", type=Path, required=True)
    attestation = commands.add_parser("attest-install")
    attestation.add_argument("--root", type=Path, required=True)
    attestation.add_argument("--distribution", type=Path, required=True)
    attestation.add_argument("--owner-uid", type=int, required=True)
    args = parser.parse_args()
    if args.command == "rehearse-install":
        path = rehearse_layout(args.destination, args.public_key.read_bytes())
        print(json.dumps({"state": "STAGED_NOT_ACTIVATED", "root": str(path)}))
        return 0
    result = attest_installation(
        args.root,
        distribution_root=args.distribution,
        expected_owner_uid=args.owner_uid,
    )
    print(canonical_json_bytes(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
