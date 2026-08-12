#!/usr/bin/env python3
"""Rehearse the V3 rollback point through a read-only exported Git archive."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = Path("docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json")


class RollbackRehearsalError(RuntimeError):
    pass


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RollbackRehearsalError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _records(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RollbackRehearsalError(f"{label} must be a list")
    return [_mapping(item, f"{label} entry") for item in cast(list[object], value)]


def rehearse(repo_root: Path) -> int:
    payload = _mapping(
        json.loads((repo_root / SNAPSHOT).read_text(encoding="utf-8")), "runtime snapshot"
    )
    safety_ref = payload.get("safetyRef")
    expected_sha = payload.get("head")
    if not isinstance(safety_ref, str) or not isinstance(expected_sha, str):
        raise RollbackRehearsalError("runtime snapshot lacks safetyRef or head")
    resolved = subprocess.run(
        ["git", "rev-parse", f"{safety_ref}^{{commit}}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if resolved != expected_sha:
        raise RollbackRehearsalError(
            f"rollback ref resolved to {resolved}, expected {expected_sha}"
        )

    tracked_inputs = _records(payload.get("trackedInputs"), "trackedInputs")
    with tempfile.TemporaryDirectory(prefix="traincapsule-v3-rollback-") as temporary:
        temporary_root = Path(temporary)
        archive = temporary_root / "rollback.tar"
        with archive.open("wb") as output:
            completed = subprocess.run(
                ["git", "archive", "--format=tar", expected_sha],
                cwd=repo_root,
                check=False,
                stdout=output,
                stderr=subprocess.PIPE,
            )
        if completed.returncode != 0:
            raise RollbackRehearsalError(
                f"git archive failed: {completed.stderr.decode('utf-8', errors='replace')}"
            )
        export = temporary_root / "export"
        export.mkdir()
        with tarfile.open(archive, "r") as reader:
            reader.extractall(export, filter="data")

        for record in tracked_inputs:
            relative = record.get("path")
            expected_bytes = record.get("bytes")
            expected_digest = record.get("sha256")
            if (
                not isinstance(relative, str)
                or not isinstance(expected_bytes, int)
                or not isinstance(expected_digest, str)
            ):
                raise RollbackRehearsalError("tracked input lacks path, bytes, or sha256")
            path = export / relative
            if not path.is_file():
                raise RollbackRehearsalError(f"rollback export lacks {relative}")
            blob = path.read_bytes()
            if len(blob) != expected_bytes or hashlib.sha256(blob).hexdigest() != expected_digest:
                raise RollbackRehearsalError(f"rollback export digest mismatch: {relative}")

    return 2 + len(tracked_inputs)


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ROOT
    if len(sys.argv) > 2:
        raise SystemExit("usage: v3_rollback_rehearsal.py [REPOSITORY_ROOT]")
    try:
        checks = rehearse(repo_root)
    except (OSError, ValueError, subprocess.SubprocessError, RollbackRehearsalError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: read-only rollback archive matched {checks} exact checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
