from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field

from .models import FactoryConfig, Stage, TaskPacket
from .util import read_json, run_command, sha256_file
from .v3.base import DIGEST_PATTERN, V3Model, sha256_digest
from .v3.source_authority import (
    emit_stale_source_proposal,
    validate_active_source_generation,
)
from .v3.work_items import WorkItem
from .yamlutil import load_yaml


class ContextPolicyError(RuntimeError):
    pass


class StaleCurrentFactError(ContextPolicyError):
    def __init__(self, message: str, *, proposal_path: Path | None = None) -> None:
        super().__init__(message)
        self.proposal_path = proposal_path


class V3ContextEntry(V3Model):
    path: str
    bytes: int = Field(ge=0)
    characters: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_class: str
    authority_sections: list[str] = Field(min_length=1)
    relevance: str
    freshness_policy: str
    freshness_status: Literal["LOCKED", "CURRENT", "STALE", "RECHECK_REQUIRED"]


class V3ContextManifest(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    work_item_id: str
    role: str
    entries: list[V3ContextEntry]
    excluded_groups: list[str]
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    max_context_chars: int = Field(ge=1)


def _active_authority_entries(repo_root: Path) -> list[V3ContextEntry]:
    """Bind the canonical generation pointer and manifest into every context."""

    active_source = validate_active_source_generation(repo_root)
    specifications = (
        (
            active_source.config_path,
            "active_generation_pointer",
            ["§generationId", "§manifestPath", "§mixedNormativeGenerationPolicy"],
            "Canonical pointer selecting the only active normative generation.",
        ),
        (
            active_source.manifest_path,
            "active_generation_manifest",
            ["§documents", "§supersession", "§integrity"],
            "Digest-bound inventory of the active normative generation.",
        ),
    )
    entries: list[V3ContextEntry] = []
    for relative, authority_class, sections, relevance in specifications:
        path = repo_root / relative
        if not path.is_file():
            raise ContextPolicyError(f"required owner authority is missing: {relative}")
        entries.append(
            V3ContextEntry(
                path=relative,
                bytes=path.stat().st_size,
                # Control-plane authority is digest-bound and sent as entry metadata;
                # its full body is not duplicated into every role's content budget.
                characters=0,
                sha256=sha256_file(path),
                authority_class=authority_class,
                authority_sections=sections,
                relevance=relevance,
                freshness_policy="manifest_locked",
                freshness_status="LOCKED",
            )
        )
    return entries


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = load_yaml(path)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _bounded(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    used = 0
    for value in values:
        clean = value.strip()
        if not clean:
            continue
        remaining = limit - used
        if remaining <= 0:
            break
        if len(clean) > remaining:
            clean = clean[: max(0, remaining - 20)] + "…[truncated]"
        result.append(clean)
        used += len(clean)
    return result


def newest_unique_findings(values: list[str]) -> list[str]:
    """Prioritize current repair evidence without mutating the durable finding history."""

    result: list[str] = []
    seen: set[str] = set()
    for value in reversed(values):
        clean = value.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _git_diff_stat(worktree: Path, base_sha: str) -> str:
    result = run_command(
        ["git", "diff", "--stat", f"{base_sha}...HEAD"],
        cwd=worktree,
        check=False,
    )
    return result.stdout.strip()


def _changed_files(worktree: Path, base_sha: str) -> list[str]:
    committed = run_command(
        ["git", "diff", "--name-only", f"{base_sha}...HEAD"],
        cwd=worktree,
        check=False,
    ).stdout.splitlines()
    untracked = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=worktree,
        check=False,
    ).stdout.splitlines()
    return sorted({line.strip() for line in [*committed, *untracked] if line.strip()})


def _index_entries(index: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    raw_key_map = (
        index.get("keys") if isinstance(index.get("keys"), dict) else index.get("contexts", {})
    )
    if not isinstance(raw_key_map, dict):
        return []
    key_map = cast(dict[str, Any], raw_key_map)
    result: list[dict[str, Any]] = []
    for key in keys:
        entry = key_map.get(key)
        if entry is None:
            result.append({"key": key, "status": "unknown"})
            continue
        if isinstance(entry, list):
            paths = [
                str(cast(dict[str, Any], value).get("path"))
                if isinstance(value, dict)
                else str(value)
                for value in cast(list[object], entry)
            ]
            sections: list[str] = []
        elif isinstance(entry, dict):
            typed_entry = cast(dict[str, Any], entry)
            paths = [str(value) for value in cast(list[object], typed_entry.get("paths", []))]
            sections = [str(value) for value in cast(list[object], typed_entry.get("sections", []))]
        else:
            paths = [str(entry)]
            sections = []
        result.append({"key": key, "status": "available", "paths": paths, "sections": sections})
    return result


def _file_manifest(
    _repo_root: Path, worktree: Path, paths: list[str], max_files: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        value = raw.split("#", 1)[0].strip()
        if not value or value.startswith(("http://", "https://")) or value in seen:
            continue
        seen.add(value)
        path = worktree / value
        if not path.is_file():
            raise ContextPolicyError(
                f"Required authority source is missing from the candidate worktree: {value}"
            )
        result.append(
            {
                "path": value,
                "exists": True,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if len(result) > max_files:
        omitted = [item["path"] for item in result[max_files:]]
        raise ContextPolicyError(
            "Required authority set exceeds max_files and cannot be silently omitted: "
            + ", ".join(omitted)
        )
    return result


def build_context_manifest(
    *,
    repo_root: Path,
    worktree: Path,
    config: FactoryConfig,
    task: TaskPacket,
    stage: Stage,
    base_sha: str,
    previous_findings: list[str] | None,
    handoff_path: str | None = None,
) -> dict[str, Any]:
    policy = _load_yaml(config.resolve(repo_root, config.context_config_path))
    index = _load_yaml(config.resolve(repo_root, config.context_index_path))
    role_defaults: object = policy.get("role_defaults", {})
    raw_role_keys: object = (
        cast(dict[str, object], role_defaults).get(stage.role.value, [])
        if isinstance(role_defaults, dict)
        else []
    )
    typed_role_keys = cast(list[object], raw_role_keys) if isinstance(raw_role_keys, list) else []
    requested_keys = list(
        dict.fromkeys([*task.context_keys, *stage.context_keys, *map(str, typed_role_keys)])
    )
    resolved = _index_entries(index, requested_keys)
    unknown_keys = [str(item["key"]) for item in resolved if item.get("status") != "available"]
    if unknown_keys:
        raise ContextPolicyError(
            "Unknown required context keys: " + ", ".join(sorted(unknown_keys))
        )

    observed_head = run_command(
        ["git", "rev-parse", "HEAD"], cwd=worktree, check=True
    ).stdout.strip()
    if observed_head != base_sha:
        raise ContextPolicyError(
            f"Context worktree HEAD {observed_head} does not match candidate base {base_sha}"
        )

    previous_limit = int(policy.get("max_failure_excerpt_chars", 12_000))
    finding_limit = int(policy.get("max_previous_findings", 12))
    prioritized = newest_unique_findings(previous_findings or [])
    findings = _bounded(prioritized[:finding_limit], previous_limit)
    diff_stat = _git_diff_stat(worktree, base_sha)
    diff_limit = int(policy.get("max_diff_stat_chars", 4_000))
    if len(diff_stat) > diff_limit:
        diff_stat = diff_stat[:diff_limit] + "\n…[diff stat truncated; inspect git directly]"

    indexed_paths: list[str] = list(task.source_of_truth)
    for item in resolved:
        indexed_paths.extend(str(value) for value in item.get("paths", []))
    indexed_paths.extend(["SOURCE_PRECEDENCE.md", "docs/CONTEXT_INDEX.yaml"])
    files = _file_manifest(repo_root, worktree, indexed_paths, int(policy.get("max_files", 36)))

    handoff: dict[str, Any] | None = None
    if handoff_path:
        handoff = read_json(Path(handoff_path), None)
        if isinstance(handoff, dict):
            # Avoid recursive or oversized historical state.
            handoff.pop("diff_excerpt", None)
        else:
            handoff = None

    manifest: dict[str, Any] = {
        "policy": "just_in_time_paths_not_transcripts",
        "risk_tier": task.risk_tier.value,
        "task_source_of_truth": task.source_of_truth,
        "context_keys": resolved,
        "files": files,
        "current_candidate": {
            "base_sha": base_sha,
            "changed_files": _changed_files(worktree, base_sha),
            "diff_stat": diff_stat,
        },
        "previous_findings": findings,
        "prior_handoff": handoff,
        "role_rules": {
            "read_named_sources_first": True,
            "retrieve_details_just_in_time": True,
            "do_not_load_entire_master_plan_without_need": True,
            "do_not_read_prior_role_transcripts": True,
            "do_not_resume_another_roles_chat": True,
            "full_logs_are_referenced_by_path": True,
        },
    }
    max_chars = stage.max_context_chars or int(policy.get("default_max_context_chars", 100_000))
    encoded = json.dumps(manifest, sort_keys=True)
    if len(encoded) > max_chars:
        manifest["previous_findings"] = _bounded(findings, max(1_000, max_chars // 4))
        manifest["current_candidate"]["diff_stat"] = "[inspect with git diff --stat]"
        encoded = json.dumps(manifest, sort_keys=True)
        if len(encoded) > max_chars:
            raise ContextPolicyError(
                "Required candidate-bound authority manifest exceeds max_context_chars; "
                "increase the stage context allowance instead of omitting sources"
            )
    return manifest


def build_v3_context_manifest(
    *,
    repo_root: Path,
    work_item: WorkItem,
    role: str,
    requested_groups: list[str],
    max_context_chars: int,
    freshness_receipts: dict[str, datetime] | None = None,
    current_fact_max_age_days: int = 30,
    now: datetime | None = None,
    stale_proposal_root: Path | None = None,
) -> V3ContextManifest:
    """Build a scoped V3 manifest with authority, relevance, digest, and freshness."""

    active_source = validate_active_source_generation(repo_root)
    if max_context_chars <= 0:
        raise ContextPolicyError("context-size budget must be positive")
    index_path = repo_root / "docs/CONTEXT_INDEX.yaml"
    index = _load_yaml(index_path)
    if index.get("version") != 4 or not isinstance(index.get("groups"), dict):
        raise ContextPolicyError("V3.1-ZH context index is missing or mixed with legacy authority")
    groups = cast(dict[str, Any], index["groups"])
    forbidden = {"advisory_career", "advisory_acquisition"}
    if forbidden & set(requested_groups):
        raise ContextPolicyError("career/acquisition context is excluded from routine work")
    missing = set(requested_groups) - set(groups)
    if missing:
        raise ContextPolicyError(f"unknown V3 context groups: {sorted(missing)}")

    observed = (now or datetime.now(UTC)).astimezone(UTC)
    freshness = freshness_receipts or {}
    entries = _active_authority_entries(repo_root)
    excluded: list[str] = sorted(forbidden)
    for group_name in requested_groups:
        group = cast(dict[str, Any], groups[group_name])
        include_roles = {str(value) for value in group.get("includeRoles", [])}
        exclude_roles = {str(value) for value in group.get("excludeRoles", [])}
        if role in exclude_roles or (include_roles and role not in include_roles):
            raise ContextPolicyError(
                f"role {role} is not permitted to consume context group {group_name}"
            )
        group_policy = str(group.get("freshnessPolicy", "manifest_locked"))
        group_authority = str(group.get("authorityClass", "unknown"))
        group_scope = str(group.get("scope", group_name))
        raw_entries_value = group.get("entries", [])
        if not isinstance(raw_entries_value, list) or not raw_entries_value:
            raise ContextPolicyError(f"required context group {group_name} has no entries")
        raw_entries = cast(list[object], raw_entries_value)
        max_sources = group.get("maxSources")
        max_characters = group.get("maxCharacters")
        if not isinstance(max_sources, int) or max_sources < 1:
            raise ContextPolicyError(f"context group {group_name} lacks a positive source budget")
        if not isinstance(max_characters, int) or max_characters < 1:
            raise ContextPolicyError(
                f"context group {group_name} lacks a positive character budget"
            )
        if len(raw_entries) > max_sources:
            raise ContextPolicyError(
                f"context group {group_name} exceeds its {max_sources}-source budget"
            )
        group_characters = 0
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                raise ContextPolicyError(f"invalid context entry in {group_name}")
            entry = cast(dict[str, Any], raw_entry)
            relative = str(entry.get("path", ""))
            path = repo_root / relative
            if not path.is_file():
                raise ContextPolicyError(
                    f"work item {work_item.work_item_id} lacks required fact/source: {relative}"
                )
            declared_digest = str(entry.get("sha256", ""))
            actual_digest = sha256_file(path)
            if not declared_digest or declared_digest != actual_digest:
                raise ContextPolicyError(
                    f"context entry digest mismatch for {relative}; refresh authority explicitly"
                )
            raw_sections = entry.get("authoritySections")
            if not isinstance(raw_sections, list):
                raise ContextPolicyError(
                    f"context entry {relative} lacks exact authority section references"
                )
            authority_sections: list[str] = []
            for value in cast(list[object], raw_sections):
                if not isinstance(value, str) or not value.strip():
                    raise ContextPolicyError(
                        f"context entry {relative} lacks exact authority section references"
                    )
                authority_sections.append(value.strip())
            if not authority_sections:
                raise ContextPolicyError(
                    f"context entry {relative} lacks exact authority section references"
                )
            source_text = path.read_text(encoding="utf-8")
            source_characters = len(source_text)
            group_characters += source_characters
            policy = str(entry.get("freshnessPolicy", group_policy))
            status: Literal["LOCKED", "CURRENT", "STALE", "RECHECK_REQUIRED"]
            if policy == "manifest_locked":
                status = "LOCKED"
            else:
                verified_at = freshness.get(group_name)
                if verified_at is None:
                    status = "RECHECK_REQUIRED"
                elif observed - verified_at.astimezone(UTC) > timedelta(
                    days=current_fact_max_age_days
                ):
                    status = "STALE"
                else:
                    status = "CURRENT"
                if status != "CURRENT":
                    proposal_path: Path | None = None
                    if stale_proposal_root is not None:
                        _, proposal_path = emit_stale_source_proposal(
                            proposal_root=stale_proposal_root,
                            work_item_id=work_item.work_item_id,
                            group=group_name,
                            freshness_status=status,
                            now=observed,
                        )
                    raise StaleCurrentFactError(
                        f"work item {work_item.work_item_id} is blocked by {status.lower()} "
                        f"current fact group {group_name}",
                        proposal_path=proposal_path,
                    )
            entries.append(
                V3ContextEntry(
                    path=relative,
                    bytes=path.stat().st_size,
                    characters=source_characters,
                    sha256=actual_digest,
                    authority_class=str(entry.get("authorityClass", group_authority)),
                    authority_sections=authority_sections,
                    relevance=str(entry.get("scope", group_scope)),
                    freshness_policy=policy,
                    freshness_status=status,
                )
            )
        if group_characters > max_characters:
            raise ContextPolicyError(
                f"context group {group_name} exceeds its {max_characters}-character budget"
            )

    ordered_entries = sorted(entries, key=lambda entry: entry.path)
    payload = active_source.source_digest.encode() + b"\n" + b"".join(
        f"{entry.path}\0{entry.sha256}\n".encode() for entry in ordered_entries
    )
    manifest = V3ContextManifest(
        work_item_id=work_item.work_item_id,
        role=role,
        entries=entries,
        excluded_groups=excluded,
        source_digest=sha256_digest(payload),
        max_context_chars=max_context_chars,
    )
    if sum(entry.characters for entry in entries) > max_context_chars:
        raise ContextPolicyError(
            f"required source context for {work_item.work_item_id} exceeds its size budget"
        )
    if len(manifest.canonical_json_bytes()) > max_context_chars:
        raise ContextPolicyError(
            f"required context for {work_item.work_item_id} exceeds its size budget"
        )
    return manifest
