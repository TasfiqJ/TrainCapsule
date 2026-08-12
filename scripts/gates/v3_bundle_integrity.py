#!/usr/bin/env python3
"""Verify the complete external V3 review bundle and its installed immutable copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = (
    ROOT
    / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11"
    / "traincapsule_v3_review_2026-08-11"
)
ACTIVE_BUNDLE = ROOT / "docs/source-of-truth/v3-2026-08-11"
REPORT = ROOT / "docs/migrations/V3_BUNDLE_INTEGRITY_REPORT.json"
MANIFEST = "FINAL_MANIFEST_V3.json"
EXPECTED_MANIFEST_SHA256 = "478b16ab78a848dda4aa6cd6d6107af634960648d1a5536982b3dc0e38da8a2d"
EXPECTED_FILE_COUNT = 30
EXPECTED_TOTAL_BYTES = 542_907

REQUIRED_ROOT_PAYLOAD = {
    "README_FIRST.md",
    "CODEX_MASTER_MIGRATION_PROMPT.md",
    "REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md",
    "TRAINCAPSULE_V3_MASTER_PLAN.md",
    "00_EXECUTIVE_BUILD_DECISION_V3.md",
    "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md",
    "04_TECHNICAL_ARCHITECTURE_V3.md",
    "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md",
    "06_COMMERCIAL_MODEL_AND_GTM_V3.md",
    "FACTORY_LOOP_REDESIGN_SPEC.md",
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md",
    "SOURCE_OF_TRUTH_MIGRATION_PLAN.md",
    "13_SOURCE_REGISTER_V3.md",
    "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md",
}
INSTALLED_IMMUTABLE_COPIES = {
    "REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md",
    "00_EXECUTIVE_BUILD_DECISION_V3.md",
    "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md",
    "04_TECHNICAL_ARCHITECTURE_V3.md",
    "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md",
    "06_COMMERCIAL_MODEL_AND_GTM_V3.md",
    "FACTORY_LOOP_REDESIGN_SPEC.md",
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md",
    "13_SOURCE_REGISTER_V3.md",
    "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md",
}


class BundleIntegrityError(RuntimeError):
    pass


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleIntegrityError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _records(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise BundleIntegrityError(f"{label} must be a list")
    return [_mapping(item, f"{label} entry") for item in cast(list[object], value)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report(
    bundle_root: Path,
    active_bundle: Path = ACTIVE_BUNDLE,
    *,
    expected_manifest_sha256: str = EXPECTED_MANIFEST_SHA256,
    expected_file_count: int = EXPECTED_FILE_COUNT,
    expected_total_bytes: int = EXPECTED_TOTAL_BYTES,
) -> dict[str, object]:
    manifest_path = bundle_root / MANIFEST
    if not manifest_path.is_file():
        raise BundleIntegrityError(f"missing authoritative manifest: {manifest_path}")
    manifest = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")), "manifest")
    if _sha256(manifest_path) != expected_manifest_sha256:
        raise BundleIntegrityError("authoritative manifest digest is not the reviewed V3 manifest")
    records = _records(manifest.get("files"), "manifest files")
    declared: dict[str, tuple[int, str, str]] = {}
    total_bytes = 0
    for record in records:
        relative = record.get("path")
        expected_bytes = record.get("bytes")
        expected_digest = record.get("sha256")
        category = record.get("category")
        if (
            not isinstance(relative, str)
            or not isinstance(expected_bytes, int)
            or not isinstance(expected_digest, str)
            or not isinstance(category, str)
        ):
            raise BundleIntegrityError("manifest entry lacks path, bytes, sha256, or category")
        if relative in declared or relative == MANIFEST or Path(relative).is_absolute():
            raise BundleIntegrityError(f"invalid or duplicate manifest path: {relative}")
        path = bundle_root / relative
        if not path.is_file():
            raise BundleIntegrityError(f"manifest payload is missing: {relative}")
        blob = path.read_bytes()
        if len(blob) != expected_bytes or hashlib.sha256(blob).hexdigest() != expected_digest:
            raise BundleIntegrityError(f"manifest byte/digest mismatch: {relative}")
        declared[relative] = (expected_bytes, expected_digest, category)
        total_bytes += expected_bytes

    actual = {
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_file()
        and path.name != MANIFEST
        and not path.name.endswith(":Zone.Identifier")
    }
    if actual != set(declared):
        raise BundleIntegrityError(
            "authoritative bundle membership mismatch: "
            f"missing={sorted(set(declared) - actual)}, extra={sorted(actual - set(declared))}"
        )
    root_payload = {path for path in declared if "/" not in path}
    if root_payload != REQUIRED_ROOT_PAYLOAD:
        raise BundleIntegrityError("authoritative root-document coverage is incomplete")
    examples = {path for path in declared if path.startswith("examples/")}
    if not examples:
        raise BundleIntegrityError("authoritative examples/ payload is empty")
    if manifest.get("fileCountExcludingManifest") != len(declared):
        raise BundleIntegrityError("manifest fileCountExcludingManifest is false")
    if manifest.get("totalBytesExcludingManifest") != total_bytes:
        raise BundleIntegrityError("manifest totalBytesExcludingManifest is false")
    if manifest.get("selfHashIncluded") is not False:
        raise BundleIntegrityError("authoritative manifest must exclude its own digest")
    if len(declared) != expected_file_count or total_bytes != expected_total_bytes:
        raise BundleIntegrityError("authoritative payload count/bytes differ from reviewed V3")

    installed: list[dict[str, object]] = []
    for relative in sorted(INSTALLED_IMMUTABLE_COPIES):
        if relative not in declared:
            raise BundleIntegrityError(f"installed source is absent from authority: {relative}")
        path = active_bundle / relative
        if not path.is_file():
            raise BundleIntegrityError(f"installed immutable copy is missing: {relative}")
        expected_bytes, expected_digest, _ = declared[relative]
        if path.stat().st_size != expected_bytes or _sha256(path) != expected_digest:
            raise BundleIntegrityError(f"installed immutable copy diverged: {relative}")
        installed.append(
            {"path": relative, "bytes": expected_bytes, "sha256": expected_digest}
        )

    return {
        "reportVersion": 1,
        "authority": "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
        "manifestSha256": _sha256(manifest_path),
        "fileCountExcludingManifest": len(declared),
        "totalBytesExcludingManifest": total_bytes,
        "rootDocuments": sorted(root_payload),
        "exampleFiles": sorted(examples),
        "files": [
            {
                "path": relative,
                "bytes": declared[relative][0],
                "sha256": declared[relative][1],
                "category": declared[relative][2],
            }
            for relative in sorted(declared)
        ],
        "installedImmutableCopies": installed,
    }


def validate_committed_report(
    report_path: Path,
    *,
    active_bundle: Path = ACTIVE_BUNDLE,
    expected_manifest_sha256: str = EXPECTED_MANIFEST_SHA256,
    expected_file_count: int = EXPECTED_FILE_COUNT,
    expected_total_bytes: int = EXPECTED_TOTAL_BYTES,
) -> int:
    report = _mapping(json.loads(report_path.read_text(encoding="utf-8")), "bundle report")
    files = _records(report.get("files"), "bundle report files")
    if report.get("reportVersion") != 1 or len(files) != report.get(
        "fileCountExcludingManifest"
    ):
        raise BundleIntegrityError("bundle report version/count is invalid")
    if (
        report.get("manifestSha256") != expected_manifest_sha256
        or report.get("fileCountExcludingManifest") != expected_file_count
        or report.get("totalBytesExcludingManifest") != expected_total_bytes
    ):
        raise BundleIntegrityError("bundle report is not bound to the reviewed V3 manifest")
    paths = {record.get("path") for record in files}
    if not REQUIRED_ROOT_PAYLOAD.issubset(paths) or not any(
        isinstance(path, str) and path.startswith("examples/") for path in paths
    ):
        raise BundleIntegrityError("bundle report silently omits required authority payload")
    installed = _records(report.get("installedImmutableCopies"), "installed copies")
    if {record.get("path") for record in installed} != INSTALLED_IMMUTABLE_COPIES:
        raise BundleIntegrityError("bundle report installed-copy coverage is incomplete")
    for record in installed:
        relative = record.get("path")
        digest = record.get("sha256")
        expected_bytes = record.get("bytes")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise BundleIntegrityError("invalid installed-copy report entry")
        path = active_bundle / relative
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or _sha256(path) != digest
        ):
            raise BundleIntegrityError(f"installed-copy report mismatch: {relative}")
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--check-report", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_report:
            expected = build_report(args.bundle.resolve())
            args.report.write_text(
                json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        if args.bundle.is_dir():
            expected = build_report(args.bundle.resolve())
            if args.check_report:
                actual = _mapping(
                    json.loads(args.report.read_text(encoding="utf-8")), "bundle report"
                )
                if actual != expected:
                    raise BundleIntegrityError("committed bundle report is stale")
            count = len(cast(list[object], expected["files"]))
        else:
            if not args.check_report:
                raise BundleIntegrityError("external bundle unavailable; use --check-report")
            count = validate_committed_report(args.report)
    except (OSError, ValueError, json.JSONDecodeError, BundleIntegrityError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: authoritative V3 bundle covers and matches all {count} payload files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
