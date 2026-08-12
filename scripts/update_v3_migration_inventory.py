#!/usr/bin/env python3
"""Regenerate the complete base-to-current file inventory in the V3 report."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/migrations/V3_MIGRATION_REPORT.md"
BASE_SHA = "6b480232fa92b069103da44c475bd17bcb3e6bd1"
START = "<!-- BEGIN GENERATED FILE INVENTORY -->"
END = "<!-- END GENERATED FILE INVENTORY -->"


def inventory() -> str:
    completed = subprocess.run(
        ["git", "diff", "--name-status", BASE_SHA, "--", "."],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    records = [line.split("\t", 1) for line in completed.stdout.splitlines()]
    tracked_paths = {path for _, path in records}
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    excluded_prefixes = (
        "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/",
        "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11.zip",
    )
    excluded_paths = {"factory/roadmap/migrations/v2_to_v3.yaml.previous"}
    for path in untracked.stdout.splitlines():
        if path in excluded_paths or path.startswith(excluded_prefixes):
            continue
        if path not in tracked_paths:
            records.append(["A", path])
    records.sort(key=lambda record: record[1])
    lines = [
        START,
        "## Complete tracked file inventory",
        "",
        f"Compared with `{BASE_SHA}`: **{len(records)} paths**.",
        "",
        "| Change | Path |",
        "|---|---|",
    ]
    lines.extend(f"| `{status}` | `{path}` |" for status, path in records)
    lines.extend([END, ""])
    return "\n".join(lines)


def updated_report() -> str:
    current = REPORT.read_text(encoding="utf-8")
    generated = inventory()
    if START in current:
        prefix, remainder = current.split(START, 1)
        _, suffix = remainder.split(END, 1)
        return prefix.rstrip() + "\n\n" + generated + suffix.lstrip("\n")
    return current.rstrip() + "\n\n" + generated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = updated_report()
    if args.check:
        return 0 if REPORT.read_text(encoding="utf-8") == expected else 1
    REPORT.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
