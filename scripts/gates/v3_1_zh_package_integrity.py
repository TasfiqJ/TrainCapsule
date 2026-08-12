#!/usr/bin/env python3
"""Verify every split payload in the authoritative V3.1-ZH remediation package."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs/migrations/V3_1_ZH_PACKAGE_INTEGRITY.json"
REPORT_SHA256 = "e759af78caf0d410b0b1f3306c016a1b1af01db52d16faa3c59b916be87fabfd"
DEFAULT_PACKAGE_ROOT = Path(
    "TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/"
    "TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _within(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    candidate.relative_to(root.resolve())
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"package payload is missing or non-regular: {relative}")
    return candidate


def validate_package(
    repo_root: Path = ROOT,
    *,
    package_root: Path | None = None,
    report_path: Path = REPORT,
) -> int:
    if _sha256(report_path) != REPORT_SHA256:
        raise ValueError("V3.1-ZH package integrity report digest mismatch")
    payload = cast(dict[str, Any], json.loads(report_path.read_text(encoding="utf-8")))
    if payload.get("schemaVersion") != 1 or payload.get("mismatchCount") != 0:
        raise ValueError("V3.1-ZH package report is not a verified schema-v1 record")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("V3.1-ZH package report must bind exactly 43 payloads")
    entries = cast(list[object], raw_entries)
    if len(entries) != 43:
        raise ValueError("V3.1-ZH package report must bind exactly 43 payloads")
    configured = Path(os.getenv("TCF_V31_REMEDIATION_ROOT", str(DEFAULT_PACKAGE_ROOT)))
    package = package_root or (configured if configured.is_absolute() else repo_root / configured)
    package_available = package.is_dir()
    if package_available:
        checksum = _within(package, "12_SHA256SUMS.txt")
        if _sha256(checksum) != payload.get("checksumLedgerSha256"):
            raise ValueError("V3.1-ZH checksum ledger digest mismatch")
    observed_amendments = 0
    observed_historical = 0
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("V3.1-ZH package entry is not an object")
        entry = cast(dict[str, Any], raw)
        logical = str(entry.get("logicalPath", ""))
        expected = str(entry.get("sha256", ""))
        if logical in seen or len(expected) != 64:
            raise ValueError(f"duplicate or malformed package entry: {logical}")
        seen.add(logical)
        if entry.get("presentInExtractedPackage") is True:
            observed_amendments += 1
            if package_available:
                path = _within(package, logical)
                if _sha256(path) != expected:
                    raise ValueError(f"V3.1-ZH package payload digest mismatch: {logical}")
        elif entry.get("presentInExtractedPackage") is False:
            path = _within(repo_root, str(entry.get("physicalResolution", "")))
            observed_historical += 1
            if _sha256(path) != expected:
                raise ValueError(f"V3.1-ZH package payload digest mismatch: {logical}")
        else:
            raise ValueError(f"package entry has no resolution class: {logical}")
        if entry.get("actualSha256") != expected:
            raise ValueError(f"V3.1-ZH package payload digest mismatch: {logical}")
    if (observed_amendments, observed_historical) != (12, 31):
        raise ValueError("V3.1-ZH package split counts differ from 12 amendments + 31 history")
    return len(seen)


def main() -> int:
    try:
        count = validate_package()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {count} V3.1-ZH split package payloads match the immutable report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
