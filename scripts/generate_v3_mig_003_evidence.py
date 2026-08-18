#!/usr/bin/env python3
"""Generate or verify deterministic evidence for V3-MIG-003."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Final, cast

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.migration_installation_evidence import (  # noqa: E402
    MigrationInstallationEvidence,
)

OLD_ROOT: Final = Path("docs/source-of-truth/v3-2026-08-11")
NEW_ROOT: Final = Path("docs/source-of-truth/v3.1-zh-2026-08-12")
OLD_MANIFEST: Final = OLD_ROOT / "FINAL_MANIFEST_V3.json"
NEW_MANIFEST: Final = NEW_ROOT / "FINAL_MANIFEST_V3_1_ZH.json"
COVERAGE: Final = NEW_ROOT / "SECTION_COVERAGE_V3_TO_V3_1_ZH.json"
EVIDENCE_PATH: Final = Path("docs/migrations/evidence/V3-MIG-003.json")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout


def _tree_digest(records: list[tuple[str, bytes]]) -> str:
    manifest = b"".join(
        path.encode("utf-8")
        + b"\0"
        + str(len(data)).encode("ascii")
        + b"\0"
        + _sha256(data).encode("ascii")
        + b"\n"
        for path, data in records
    )
    return _sha256(manifest)


def _current_tree(repo_root: Path, relative_root: Path) -> tuple[int, str]:
    absolute_root = repo_root / relative_root
    if not absolute_root.is_dir() or absolute_root.is_symlink():
        raise ValueError(f"authority root is missing or unsafe: {relative_root}")
    records: list[tuple[str, bytes]] = []
    for path in sorted(absolute_root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"authority tree contains a symlink: {path.relative_to(repo_root)}")
        if path.is_file():
            records.append((path.relative_to(repo_root).as_posix(), path.read_bytes()))
    if not records:
        raise ValueError(f"authority root has no files: {relative_root}")
    return len(records), _tree_digest(records)


def _commit_tree(repo_root: Path, commit: str, relative_root: Path) -> tuple[int, str]:
    raw_paths = _git(
        repo_root,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        commit,
        "--",
        relative_root.as_posix(),
    )
    paths = sorted(item.decode("utf-8") for item in raw_paths.split(b"\0") if item)
    if not paths:
        raise ValueError(f"authority root is absent at {commit}: {relative_root}")
    records = [(path, _git(repo_root, "show", f"{commit}:{path}")) for path in paths]
    return len(records), _tree_digest(records)


def _installation_commit(repo_root: Path, manifest: Path) -> str:
    output = _git(
        repo_root,
        "log",
        "--diff-filter=A",
        "--reverse",
        "--format=%H",
        "--",
        manifest.as_posix(),
    ).decode("ascii")
    commits = [line.strip() for line in output.splitlines() if line.strip()]
    if len(commits) != 1:
        raise ValueError(
            f"expected one installation commit for {manifest}, found {len(commits)}"
        )
    return commits[0]


def build_evidence(repo_root: Path) -> MigrationInstallationEvidence:
    old_manifest_bytes = (repo_root / OLD_MANIFEST).read_bytes()
    new_manifest_bytes = (repo_root / NEW_MANIFEST).read_bytes()
    coverage_bytes = (repo_root / COVERAGE).read_bytes()
    old_manifest = cast(dict[str, object], json.loads(old_manifest_bytes))
    coverage = cast(dict[str, object], json.loads(coverage_bytes))

    migration_base = str(old_manifest.get("migrationBaseSha", ""))
    old_install = _installation_commit(repo_root, OLD_MANIFEST)
    new_install = _installation_commit(repo_root, NEW_MANIFEST)
    old_count, old_current_tree = _current_tree(repo_root, OLD_ROOT)
    new_count, new_current_tree = _current_tree(repo_root, NEW_ROOT)
    old_install_count, old_install_tree = _commit_tree(repo_root, old_install, OLD_ROOT)
    new_install_count, new_install_tree = _commit_tree(repo_root, new_install, NEW_ROOT)
    old_at_new_count, old_at_new_tree = _commit_tree(repo_root, new_install, OLD_ROOT)
    if old_at_new_count != old_count or old_at_new_tree != old_current_tree:
        raise ValueError("old authority tree changed after the V3.1-ZH installation commit")

    totals = coverage.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("coverage totals are missing")
    typed_totals = cast(dict[str, object], totals)
    source_heading_count = typed_totals.get("sourceHeadingCount")
    mapped_heading_count = typed_totals.get("mappedHeadingCount")
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "workItemId": "V3-MIG-003",
        "evidenceType": "DETERMINISTIC_SOURCE_INSTALLATION",
        "migrationBaseCommit": migration_base,
        "oldAuthority": {
            "root": OLD_ROOT.as_posix(),
            "fileCount": old_count,
            "treeSha256": old_current_tree,
            "installationCommit": old_install,
            "treeAtInstallationSha256": old_install_tree,
        },
        "newAuthority": {
            "root": NEW_ROOT.as_posix(),
            "fileCount": new_count,
            "treeSha256": new_current_tree,
            "installationCommit": new_install,
            "treeAtInstallationSha256": new_install_tree,
        },
        "preservedOldAuthority": {
            "comparisonCommit": new_install,
            "treeAtComparisonSha256": old_at_new_tree,
            "currentTreeSha256": old_current_tree,
            "noPostInstallMutation": True,
        },
        "oldManifestPath": OLD_MANIFEST.as_posix(),
        "oldManifestSha256": _sha256(old_manifest_bytes),
        "newManifestPath": NEW_MANIFEST.as_posix(),
        "newManifestSha256": _sha256(new_manifest_bytes),
        "coverage": {
            "path": COVERAGE.as_posix(),
            "sha256": _sha256(coverage_bytes),
            "sourceHeadingCount": source_heading_count,
            "mappedHeadingCount": mapped_heading_count,
            "complete": source_heading_count == mapped_heading_count,
        },
    }
    evidence = MigrationInstallationEvidence.model_validate(payload)
    if old_install_count < 1 or new_install_count < 1:
        raise ValueError("installation commit authority trees are empty")
    return evidence


def rendered_evidence(repo_root: Path) -> str:
    payload = build_evidence(repo_root).model_dump(mode="json", by_alias=True)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    target = repo_root / EVIDENCE_PATH
    rendered = rendered_evidence(repo_root)
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            raise SystemExit("V3-MIG-003 installation evidence is stale or invalid")
        print("PASS: V3-MIG-003 installation evidence is exact and replayable")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {target.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
