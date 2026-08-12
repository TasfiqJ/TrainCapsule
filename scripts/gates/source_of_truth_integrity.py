#!/usr/bin/env python3
"""Fail closed when the active TrainCapsule V3 authority is ambiguous or modified."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_v3_manifest import (  # noqa: E402
    ACTIVE_FILES,
    BUNDLE_RELATIVE,
    MANIFEST_NAME,
    NORMATIVE_ORDER,
    build_manifest,
    canonical_text_bytes,
)
from tcfactory.yamlutil import load_yaml  # noqa: E402

REQUIRED_GROUPS = {
    "product_normative",
    "technical_architecture",
    "trust_core",
    "commercial",
    "roadmap",
    "current_facts",
    "factory_control",
    "commercial_wedge",
    "native_baseline",
    "pre_collective_pack",
    "market_evidence",
    "factory_controller",
    "advisory_acquisition",
    "advisory_career",
}
LOCAL_PATH_PATTERNS = (
    re.compile(r"(?i)[a-z]:\\(?:users|home)\\"),
    re.compile(r"(?i)\\\\wsl(?:\.localhost|\$)\\"),
    re.compile(r"(?<![\w.-])/(?:home|users)/[\w.-]+/"),
)


class SourceIntegrityError(RuntimeError):
    pass


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceIntegrityError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise SourceIntegrityError(f"{label} must be a list")
    return cast(list[object], value)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceIntegrityError(f"unreadable JSON {path}: {exc}") from exc


def _validate_manifest(repo_root: Path) -> dict[str, Any]:
    bundle = repo_root / BUNDLE_RELATIVE
    manifest_path = bundle / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SourceIntegrityError(f"missing V3 manifest: {manifest_path}")
    payload = _load_json(manifest_path)
    records = _list(payload.get("files"), "manifest files")

    paths: list[str] = []
    logical_ids: list[str] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, f"manifest files[{index}]")
        path = record.get("path")
        logical_id = record.get("logicalId")
        if not isinstance(path, str) or not isinstance(logical_id, str):
            raise SourceIntegrityError("manifest file records require string path and logicalId")
        paths.append(path)
        logical_ids.append(logical_id)
    if MANIFEST_NAME in paths:
        raise SourceIntegrityError("manifest self-hash is forbidden")
    if len(logical_ids) != len(set(logical_ids)):
        raise SourceIntegrityError("duplicate active logical ID in V3 manifest")
    if any("(1)" in path for path in paths):
        raise SourceIntegrityError("active `(1)` duplicate is forbidden")

    actual_names = {path.name for path in bundle.iterdir() if path.is_file()}
    expected_names = set(ACTIVE_FILES) | {MANIFEST_NAME}
    if actual_names != expected_names:
        raise SourceIntegrityError(
            "active V3 bundle membership mismatch: "
            f"missing={sorted(expected_names - actual_names)}, "
            f"extra={sorted(actual_names - expected_names)}"
        )

    for name in ACTIVE_FILES:
        path = bundle / name
        canonical = canonical_text_bytes(path)
        if path.read_bytes() != canonical:
            raise SourceIntegrityError(f"active V3 text is not canonical UTF-8 LF: {name}")

    migration_base = payload.get("migrationBaseSha")
    generated_at = payload.get("generatedAt")
    if not isinstance(migration_base, str) or not isinstance(generated_at, str):
        raise SourceIntegrityError("manifest lacks migrationBaseSha or generatedAt")
    expected = build_manifest(
        repo_root,
        migration_base_sha=migration_base,
        generated_at=generated_at,
    )
    if payload != expected:
        raise SourceIntegrityError("V3 manifest content or canonical hashes do not match")
    if payload.get("selfHashIncluded") is not False:
        raise SourceIntegrityError("manifest must explicitly exclude its own hash")
    if payload.get("normativeOrder") != NORMATIVE_ORDER:
        raise SourceIntegrityError("V3 normative order is invalid")
    return payload


def _validate_context(repo_root: Path) -> None:
    path = repo_root / "docs/CONTEXT_INDEX.yaml"
    payload = _mapping(load_yaml(path), str(path))
    if payload.get("version") != 3:
        raise SourceIntegrityError("context index must be version 3")
    if payload.get("activeBundle") != BUNDLE_RELATIVE.as_posix():
        raise SourceIntegrityError("context index does not select the V3 bundle")
    groups = _mapping(payload.get("groups"), "context groups")
    if set(groups) != REQUIRED_GROUPS:
        raise SourceIntegrityError(
            f"context groups mismatch: missing={sorted(REQUIRED_GROUPS - set(groups))}, "
            f"extra={sorted(set(groups) - REQUIRED_GROUPS)}"
        )
    for group_name, raw_group in groups.items():
        group = _mapping(raw_group, f"context group {group_name}")
        for field in (
            "authorityClass",
            "scope",
            "includeRoles",
            "excludeRoles",
            "freshnessPolicy",
            "maxSources",
            "maxCharacters",
            "entries",
        ):
            if field not in group:
                raise SourceIntegrityError(f"context group {group_name} lacks {field}")
        entries = _list(group["entries"], f"context group {group_name} entries")
        max_sources = group["maxSources"]
        max_characters = group["maxCharacters"]
        if group_name.startswith("advisory_"):
            if entries or max_sources != 0 or max_characters != 0:
                raise SourceIntegrityError(f"advisory context group {group_name} must be empty")
            continue
        if not isinstance(max_sources, int) or not 0 < len(entries) <= max_sources:
            raise SourceIntegrityError(f"context group {group_name} violates its source budget")
        if not isinstance(max_characters, int) or max_characters < 1:
            raise SourceIntegrityError(f"context group {group_name} lacks a character budget")
        observed_characters = 0
        for index, raw_entry in enumerate(entries):
            entry = _mapping(raw_entry, f"{group_name} entries[{index}]")
            required = {
                "path",
                "sha256",
                "authorityClass",
                "authoritySections",
                "scope",
                "freshnessPolicy",
            }
            missing = required - set(entry)
            if missing:
                raise SourceIntegrityError(
                    f"context entry {group_name}[{index}] lacks {sorted(missing)}"
                )
            source = entry["path"]
            if not isinstance(source, str) or not (repo_root / source).is_file():
                raise SourceIntegrityError(f"unresolved V3 context path: {source}")
            source_path = repo_root / source
            actual_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if entry["sha256"] != actual_digest:
                raise SourceIntegrityError(f"context entry digest mismatch: {source}")
            sections = _list(entry["authoritySections"], f"{group_name}[{index}] sections")
            if not sections or any(
                not isinstance(value, str) or not value.startswith("§")
                for value in sections
            ):
                raise SourceIntegrityError(
                    f"context entry lacks exact authority sections: {source}"
                )
            observed_characters += len(source_path.read_text(encoding="utf-8"))
            if "final-2026-08-09" in source or "(1)" in source:
                raise SourceIntegrityError(
                    f"historical or duplicate file is active context: {source}"
                )
            authority_class = entry["authorityClass"]
            if (
                group_name in {"current_facts", "market_evidence"}
                and authority_class != "current_fact"
            ):
                raise SourceIntegrityError(
                    "current factual authority is mixed with normative authority"
                )
            factual_groups = {
                "current_facts",
                "market_evidence",
                "commercial_wedge",
                "native_baseline",
            }
            if group_name not in factual_groups and authority_class == "current_fact":
                raise SourceIntegrityError("current factual authority appears in a normative group")
        if observed_characters > max_characters:
            raise SourceIntegrityError(f"context group {group_name} violates its character budget")


def _validate_precedence(repo_root: Path) -> None:
    text = (repo_root / "SOURCE_PRECEDENCE.md").read_text(encoding="utf-8")
    active = BUNDLE_RELATIVE.as_posix() + "/"
    if active not in text:
        raise SourceIntegrityError("SOURCE_PRECEDENCE does not identify the active V3 bundle")
    if "final-2026-08-09/` is immutable historical evidence" not in text:
        raise SourceIntegrityError("historical bundle is not explicitly classified as archive")
    if re.search(r"final-2026-08-09/.*active (?:product )?authority", text, re.IGNORECASE):
        raise SourceIntegrityError("old bundle is treated as active authority")
    for required in (
        "config/owner_directives.yaml",
        "docs/migrations/V3_OWNER_DIRECTIVES.md",
        "explicitly override",
        "main-only",
    ):
        if required not in text:
            raise SourceIntegrityError(
                f"owner-directed authority deviation is undocumented: {required}"
            )


def _validate_owner_directives(repo_root: Path) -> None:
    path = repo_root / "config/owner_directives.yaml"
    payload = _mapping(load_yaml(path), str(path))
    if payload.get("version") != 3:
        raise SourceIntegrityError("owner directives must be version 3")
    directives = _mapping(payload.get("directives"), "owner directives")
    expected = {
        "unattendedOperation": "REQUIRED",
        "humanIntervention": "FORBIDDEN",
        "publicationBranch": "main",
        "nonMainPushes": "FORBIDDEN",
        "pullRequestDependency": "FORBIDDEN",
        "externalEvidencePolicy": "NEVER_FABRICATE",
        "missingEvidenceResult": "UNKNOWN",
        "scopedBlockersDoNotStopIndependentLanes": True,
    }
    if directives != expected:
        raise SourceIntegrityError(
            "owner directives do not match the zero-human/main-only authority"
        )


def _walk_records(value: object) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        result.append(cast(dict[str, Any], mapping))
        for child in mapping.values():
            result.extend(_walk_records(child))
    elif isinstance(value, list):
        for child in cast(list[object], value):
            result.extend(_walk_records(child))
    return result


def _validate_no_synthetic_commercial_completion(repo_root: Path) -> None:
    roadmap = repo_root / "factory/roadmap"
    if not roadmap.is_dir():
        return
    for path in sorted({*roadmap.rglob("*.yaml"), *roadmap.rglob("*.yml")}):
        payload = load_yaml(path)
        for record in _walk_records(payload):
            if (
                str(record.get("type", "")).upper() == "COMMERCIAL"
                and str(record.get("status", "")).upper() in {"COMPLETED", "PASSED"}
                and record.get("syntheticTestOnly") is True
            ):
                raise SourceIntegrityError(
                    f"synthetic evidence advances commercial completion: {path}"
                )


def _validate_no_local_paths(repo_root: Path) -> None:
    targets = [
        *(repo_root / BUNDLE_RELATIVE).glob("*.md"),
        repo_root / "SOURCE_PRECEDENCE.md",
        repo_root / "docs/CONTEXT_INDEX.yaml",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in LOCAL_PATH_PATTERNS):
            raise SourceIntegrityError(f"absolute machine-local path in active authority: {path}")


def validate_repository(repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    _validate_manifest(repo_root)
    _validate_context(repo_root)
    _validate_precedence(repo_root)
    _validate_owner_directives(repo_root)
    _validate_no_synthetic_commercial_completion(repo_root)
    _validate_no_local_paths(repo_root)


def main() -> int:
    repo_root = Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT
    if len(sys.argv) > 2:
        raise SystemExit("usage: source_of_truth_integrity.py [REPOSITORY_ROOT]")
    try:
        validate_repository(repo_root)
    except (OSError, ValueError, SourceIntegrityError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: TrainCapsule V3 source authority and {len(ACTIVE_FILES)} files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
