#!/usr/bin/env python3
"""Generate the canonical TrainCapsule V3 source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
BUNDLE_RELATIVE: Final = Path("docs/source-of-truth/v3-2026-08-11")
MANIFEST_NAME: Final = "FINAL_MANIFEST_V3.json"
ACTIVE_FILES: Final[dict[str, str]] = {
    "README.md": "metadata",
    "00_EXECUTIVE_BUILD_DECISION_V3.md": "normative_executive",
    "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md": "normative_product",
    "04_TECHNICAL_ARCHITECTURE_V3.md": "normative_architecture",
    "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md": "normative_trust",
    "06_COMMERCIAL_MODEL_AND_GTM_V3.md": "normative_commercial",
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md": "normative_roadmap",
    "13_SOURCE_REGISTER_V3.md": "current_fact",
    "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md": "executor_policy",
    "FACTORY_LOOP_REDESIGN_SPEC.md": "normative_factory",
    "REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md": "audit_evidence",
}
NORMATIVE_ORDER: Final[list[str]] = [
    "00_EXECUTIVE_BUILD_DECISION_V3.md",
    "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md",
    "04_TECHNICAL_ARCHITECTURE_V3.md",
    "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md",
    "06_COMMERCIAL_MODEL_AND_GTM_V3.md",
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md",
    "FACTORY_LOOP_REDESIGN_SPEC.md",
    "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md",
]


def canonical_text_bytes(path: Path) -> bytes:
    """Return normalized UTF-8 LF text with exactly one trailing newline."""

    text = path.read_text(encoding="utf-8-sig")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    return normalized.encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _logical_id(name: str) -> str:
    return Path(name).stem.lower().replace("-", "_")


def _base_commit_time(repo_root: Path, migration_base_sha: str) -> str:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", migration_base_sha],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = datetime.fromisoformat(result.stdout.strip()).astimezone(
        timezone.utc  # noqa: UP017 - this gate also runs under the host's Python 3.10
    )
    return parsed.isoformat().replace("+00:00", "Z")


def build_manifest(
    repo_root: Path,
    *,
    migration_base_sha: str,
    generated_at: str | None = None,
) -> dict[str, object]:
    bundle = repo_root / BUNDLE_RELATIVE
    records: list[dict[str, object]] = []
    for name, authority_class in ACTIVE_FILES.items():
        path = bundle / name
        if not path.is_file():
            raise ValueError(f"required V3 source file is missing: {path}")
        data = canonical_text_bytes(path)
        records.append(
            {
                "path": name,
                "logicalId": _logical_id(name),
                "sha256": _sha256(data),
                "bytes": len(data),
                "authorityClass": authority_class,
            }
        )
    return {
        "manifestVersion": 3,
        "bundleVersion": "v3-2026-08-11",
        "generatedAt": generated_at or _base_commit_time(repo_root, migration_base_sha),
        "migrationBaseSha": migration_base_sha,
        "supersededBundle": "docs/source-of-truth/final-2026-08-09",
        "hashAlgorithm": "sha256",
        "canonicalization": {
            "textEncoding": "utf-8",
            "lineEndings": "lf",
            "trailingNewline": True,
        },
        "selfHashIncluded": False,
        "normativeOrder": NORMATIVE_ORDER,
        "currentFactFiles": ["13_SOURCE_REGISTER_V3.md"],
        "files": records,
    }


def _existing_generated_at(manifest_path: Path) -> str | None:
    if not manifest_path.is_file():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    value = payload.get("generatedAt")
    return value if isinstance(value, str) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--migration-base-sha")
    parser.add_argument("--generated-at")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    manifest_path = repo_root / BUNDLE_RELATIVE / MANIFEST_NAME
    if args.migration_base_sha:
        migration_base_sha = str(args.migration_base_sha)
    elif manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        migration_base_sha = str(existing.get("migrationBaseSha", ""))
    else:
        raise SystemExit("--migration-base-sha is required when creating the manifest")
    if len(migration_base_sha) != 40:
        raise SystemExit("migration base SHA must be a full 40-character commit")

    generated_at = (
        str(args.generated_at)
        if args.generated_at
        else _existing_generated_at(manifest_path)
    )
    payload = build_manifest(
        repo_root,
        migration_base_sha=migration_base_sha,
        generated_at=generated_at,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not manifest_path.is_file() or manifest_path.read_text(encoding="utf-8") != rendered:
            raise SystemExit("V3 source manifest is stale; regenerate it")
        print(f"PASS: V3 source manifest matches {len(ACTIVE_FILES)} canonical files")
        return 0

    manifest_path.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {manifest_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
