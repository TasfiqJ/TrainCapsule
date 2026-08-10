#!/usr/bin/env python3
"""Fail when any repository YAML file contains duplicate mapping keys or invalid syntax."""

from __future__ import annotations

import sys
from pathlib import Path

from tcfactory.yamlutil import DuplicateYamlKeyError, load_yaml

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", ".pytest_cache", "factory/worktrees", "factory/artifacts"}


def excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    return any(relative == part or relative.startswith(part + "/") for part in EXCLUDED_PARTS)


def main() -> int:
    failed: list[str] = []
    paths = sorted({*ROOT.rglob("*.yaml"), *ROOT.rglob("*.yml")})
    for path in paths:
        if excluded(path):
            continue
        try:
            load_yaml(path)
        except (DuplicateYamlKeyError, ValueError, OSError) as exc:
            failed.append(f"{path.relative_to(ROOT)}: {exc}")
    if failed:
        print("YAML validation failed:", file=sys.stderr)
        for line in failed:
            print(f"- {line}", file=sys.stderr)
        return 1
    print(f"Validated {sum(not excluded(path) for path in paths)} YAML files with unique keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
