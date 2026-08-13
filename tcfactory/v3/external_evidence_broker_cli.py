"""Root-broker CLI for automated external-evidence authority promotion."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from tcfactory.v3.external_evidence_authority import ExternalEvidenceAuthorityBroker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged-root", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    arguments = parser.parse_args()
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        parser.error("external evidence authority broker must run as root")
    state = ExternalEvidenceAuthorityBroker(arguments.ledger).promote_signed_snapshot(
        staged_root=arguments.staged_root,
        public_key=arguments.public_key,
    )
    print(state.canonical_digest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
