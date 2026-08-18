#!/usr/bin/env python3
"""Fail closed when the active TrainCapsule V3 authority is ambiguous or modified."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.source_authority import validate_active_source_generation  # noqa: E402
from tcfactory.yamlutil import load_yaml  # noqa: E402

# V3.1-ZH is selected only by config/active_generation.yaml. These compatibility
# constants keep the additional context/precedence checks generation-scoped.
BUNDLE_RELATIVE = Path("docs/source-of-truth/v3.1-zh-2026-08-12")

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


def _validate_context(repo_root: Path) -> None:
    path = repo_root / "docs/CONTEXT_INDEX.yaml"
    payload = _mapping(load_yaml(path), str(path))
    if payload.get("version") != 4:
        raise SourceIntegrityError("context index must be V3.1-ZH version 4")
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
        repo_root / "docs/CONTEXT_INDEX.yaml",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in LOCAL_PATH_PATTERNS):
            raise SourceIntegrityError(f"absolute machine-local path in active authority: {path}")


def validate_repository(repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    validate_active_source_generation(repo_root)
    _validate_context(repo_root)
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
    print("PASS: TrainCapsule V3.1-ZH active source authority verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
