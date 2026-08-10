from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .models import FactoryConfig, Stage, TaskPacket
from .util import read_json, run_command, sha256_file
from .yamlutil import load_yaml


class ContextPolicyError(RuntimeError):
    pass


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
    repo_root: Path, worktree: Path, paths: list[str], max_files: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        value = raw.split("#", 1)[0].strip()
        if not value or value.startswith(("http://", "https://")) or value in seen:
            continue
        seen.add(value)
        path = worktree / value
        if not path.exists():
            path = repo_root / value
        exists = path.is_file()
        result.append(
            {
                "path": value,
                "exists": exists,
                "bytes": path.stat().st_size if exists else 0,
                "sha256": sha256_file(path) if exists else None,
            }
        )
        if len(result) >= max_files:
            break
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

    previous_limit = int(policy.get("max_failure_excerpt_chars", 12_000))
    finding_limit = int(policy.get("max_previous_findings", 12))
    findings = _bounded((previous_findings or [])[:finding_limit], previous_limit)
    diff_stat = _git_diff_stat(worktree, base_sha)
    diff_limit = int(policy.get("max_diff_stat_chars", 4_000))
    if len(diff_stat) > diff_limit:
        diff_stat = diff_stat[:diff_limit] + "\n…[diff stat truncated; inspect git directly]"

    indexed_paths: list[str] = list(task.source_of_truth)
    for item in resolved:
        indexed_paths.extend(str(value) for value in item.get("paths", []))
    indexed_paths.extend(["docs/SOURCE_AUTHORITY.md", "docs/DOCUMENT_LOADING_POLICY.md"])
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
        manifest["files"] = files[: max(8, len(files) // 2)]
    return manifest
