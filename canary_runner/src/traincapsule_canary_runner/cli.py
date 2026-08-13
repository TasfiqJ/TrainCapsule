"""Bounded CLI matching tcfactory ExternalCanaryRunner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import MandatoryCanaryId
from .runner import execute


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument(
        "--canary", required=True, choices=[item.value for item in MandatoryCanaryId]
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    args = parser.parse_args()
    result = execute(
        canary_id=MandatoryCanaryId(args.canary),
        run_id=args.run_id,
        repo=args.repo,
        runtime=args.runtime_root,
        artifacts=args.artifact_root,
        main_sha=args.main_sha,
        tree_sha=args.tree_sha,
        runner_executable=Path(sys.argv[0]).resolve(strict=True),
    )
    sys.stdout.write(json.dumps(result.model_dump(mode="json", by_alias=True), sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
