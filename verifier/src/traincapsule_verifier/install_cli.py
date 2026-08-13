"""Public inert installer-plan entrypoint; it never applies system changes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bootstrap import production_install_manifest, render_systemd_units, staged_tree_digest
from .canonical import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-verifier-plan-install")
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    if args.stage is None:
        print(canonical_json_bytes(production_install_manifest()).decode(), end="")
        return 0
    paths = render_systemd_units(args.stage)
    print(json.dumps({"state": "STAGED_NOT_ACTIVATED", "digest": staged_tree_digest(paths)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
