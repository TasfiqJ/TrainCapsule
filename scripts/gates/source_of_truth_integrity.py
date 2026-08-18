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

from tcfactory.v3.source_authority import validate_active_source_generation  # noqa: E402
from tcfactory.yamlutil import load_yaml  # noqa: E402

# V3.1-ZH is selected only by config/active_generation.yaml. These compatibility
# constants keep the additional context/precedence checks generation-scoped.
BUNDLE_RELATIVE = Path("docs/source-of-truth/v3.1-zh-2026-08-12")
PRECEDENCE_POLICY_RELATIVE = Path("config/source_precedence.yaml")
# Bound to the canonical JSON form of config/source_precedence.yaml with
# policyDigest omitted. Policy edits must deliberately update this verifier.
EXPECTED_PRECEDENCE_POLICY_DIGEST = (
    "e825bb492e55ea606bc56e0bc0b1e8a79b88f0f9ef0003399019e71f1fc196a9"
)
EXPECTED_NORMATIVE_ORDER = [
    "00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md",
    "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md",
    "04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md",
    "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md",
    "06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md",
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md",
    "FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md",
    "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md",
]

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


def canonical_policy_digest(payload: dict[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "policyDigest"}
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_precedence_policy(repo_root: Path) -> dict[str, Any]:
    path = repo_root / PRECEDENCE_POLICY_RELATIVE
    payload = _mapping(load_yaml(path), str(path))
    observed = canonical_policy_digest(payload)
    if payload.get("policyDigest") != observed:
        raise SourceIntegrityError("source precedence policy self-digest mismatch")
    if observed != EXPECTED_PRECEDENCE_POLICY_DIGEST:
        raise SourceIntegrityError("source precedence policy is not verifier-bound")
    if payload.get("activeGeneration") != "traincapsule-v3.1-zh-2026-08-12":
        raise SourceIntegrityError("source precedence policy selects another generation")
    if payload.get("activeManifest") != (
        BUNDLE_RELATIVE / "FINAL_MANIFEST_V3_1_ZH.json"
    ).as_posix():
        raise SourceIntegrityError("source precedence policy selects another manifest")
    narrative = payload.get("narrativePath")
    if not isinstance(narrative, str):
        raise SourceIntegrityError("source precedence narrative path is missing")
    narrative_path = repo_root / narrative
    if hashlib.sha256(narrative_path.read_bytes()).hexdigest() != payload.get(
        "narrativeSha256"
    ):
        raise SourceIntegrityError("source precedence narrative digest mismatch")

    order = _list(payload.get("normativeOrder"), "normative precedence order")
    if not order or any(not isinstance(item, str) for item in order):
        raise SourceIntegrityError("normative precedence order must contain paths")
    if len(order) != len(set(order)):
        raise SourceIntegrityError("normative precedence order contains duplicates")
    if order != EXPECTED_NORMATIVE_ORDER:
        raise SourceIntegrityError("normative precedence order does not match canonical order")
    manifest = json.loads((repo_root / str(payload["activeManifest"])).read_text("utf-8"))
    documents = _list(_mapping(manifest, "active manifest").get("documents"), "manifest documents")
    manifest_names = [
        Path(str(_mapping(item, "manifest document").get("path", ""))).name
        for item in documents
    ]
    if any(manifest_names.count(str(name)) != 1 for name in order):
        raise SourceIntegrityError("normative precedence source is missing or duplicated")
    return payload


def _validate_context(repo_root: Path, precedence: dict[str, Any]) -> None:
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
    routing = _mapping(load_yaml(repo_root / "config/context.yaml"), "context routing policy")
    for flag in (
        "requireEntryDigest",
        "requireAuthoritySections",
        "rejectRoleMismatch",
        "rejectStaleCurrentFacts",
    ):
        if routing.get(flag) is not True:
            raise SourceIntegrityError(f"context routing policy must enable {flag}")
    role_defaults = _mapping(routing.get("roleDefaultGroups"), "role default groups")
    for role, raw_defaults in role_defaults.items():
        defaults = _list(raw_defaults, f"role defaults for {role}")
        if len(defaults) != len(set(defaults)):
            raise SourceIntegrityError(f"role {role} contains duplicate default groups")
        for group_name in defaults:
            if not isinstance(group_name, str):
                raise SourceIntegrityError(f"role {role} default group must be a string")
            if group_name not in groups:
                raise SourceIntegrityError(f"role {role} selects unknown group {group_name}")
            group = _mapping(groups[group_name], f"context group {group_name}")
            if role not in _list(group.get("includeRoles"), f"{group_name} includeRoles"):
                raise SourceIntegrityError(f"role/group authority mismatch: {role}/{group_name}")
            if role in _list(group.get("excludeRoles"), f"{group_name} excludeRoles"):
                raise SourceIntegrityError(f"role/group authority mismatch: {role}/{group_name}")

    normative_only = set(_list(precedence.get("normativeOnlyGroups"), "normative-only groups"))
    strict_facts = set(_list(precedence.get("strictCurrentFactGroups"), "current-fact groups"))
    mixed = set(_list(precedence.get("mixedEvidenceGroups"), "mixed evidence groups"))
    classified = normative_only | strict_facts | mixed
    unclassified = set(groups) - classified - {"advisory_acquisition", "advisory_career"}
    if unclassified:
        raise SourceIntegrityError(f"unclassified context authority groups: {sorted(unclassified)}")
    fact_class = precedence.get("currentFactAuthorityClass")
    fact_freshness = precedence.get("currentFactFreshnessPolicy")
    stale_statuses = set(_list(precedence.get("staleStatuses"), "stale fact statuses"))

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
        seen_sources: set[str] = set()
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
            if source in seen_sources:
                raise SourceIntegrityError(f"duplicate context source in {group_name}: {source}")
            seen_sources.add(source)
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
            if group_name in strict_facts and authority_class != fact_class:
                raise SourceIntegrityError(
                    "current factual authority is mixed with normative authority"
                )
            if group_name in normative_only and authority_class == fact_class:
                raise SourceIntegrityError("current factual authority appears in a normative group")
            if authority_class == fact_class:
                if entry.get("freshnessPolicy") != fact_freshness:
                    raise SourceIntegrityError(
                        "current factual authority lacks required freshness policy"
                    )
                status = str(entry.get("freshnessStatus", entry.get("status", "CURRENT"))).upper()
                if status in stale_statuses:
                    raise SourceIntegrityError(f"stale current fact is active context: {source}")
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
    precedence = validate_precedence_policy(repo_root)
    _validate_context(repo_root, precedence)
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
