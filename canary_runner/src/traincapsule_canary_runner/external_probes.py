"""Concrete live probes for the two externally gated Phase 16 canaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

POLICY_PATH = Path("/etc/traincapsule-canary-runner/live-probes.json")


class _ProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    executable: str = Field(pattern=r"^/usr/libexec/traincapsule-canary-[a-z0-9_-]+$")
    executable_digest: str = Field(alias="executableDigest", pattern=r"^sha256:[0-9a-f]{64}$")
    token_file: str = Field(
        alias="tokenFile",
        pattern=r"^/var/lib/traincapsule-canary-secrets/[a-z0-9_-]+$",
    )


class _GitHubProbeConfig(_ProbeConfig):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    workflow: str = Field(pattern=r"^traincapsule-[a-z0-9_-]+\.yml$")


class _LiveProbePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    schema_version: str = Field(alias="schemaVersion", pattern=r"^3\.1$")
    claude: _ProbeConfig
    github: _GitHubProbeConfig


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _trusted_executable(path: Path, expected_digest: str) -> None:
    observed = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != 0
        or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or not observed.st_mode & stat.S_IXUSR
        or _digest(path.read_bytes()) != expected_digest
    ):
        raise ValueError("external probe executable is not root-pinned")


def _load_policy() -> _LiveProbePolicy:
    observed = POLICY_PATH.stat(follow_symlinks=False)
    if (
        POLICY_PATH.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != 0
        or observed.st_nlink != 1
        or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ValueError("live canary policy is not a root-owned immutable file")
    return _LiveProbePolicy.model_validate_json(POLICY_PATH.read_bytes(), strict=True)


def _read_controller_secret(path: Path) -> str:
    observed = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or observed.st_nlink != 1
        or observed.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
    ):
        raise ValueError("canary credential is not confined to the controller principal")
    secret = path.read_text().strip()
    if not secret or len(secret) > 16_384:
        raise ValueError("canary credential is absent or oversized")
    return secret


def _claude(args: argparse.Namespace) -> dict[str, object]:
    config = _load_policy().claude
    executable = Path(config.executable)
    token_file = Path(config.token_file)
    _trusted_executable(executable, config.executable_digest)
    output = args.artifact_root / "real-claude-mechanical.txt"
    workspace_output = args.repo / f".traincapsule-canary-{args.run_id.lower()}.txt"
    if workspace_output.exists() or workspace_output.is_symlink():
        raise ValueError("Claude canary workspace output already exists")
    prompt = (
        "Mechanical canary only. Create exactly the file "
        f"{workspace_output} containing one line: TRAINCAPSULE_CLAUDE_CANARY_OK. "
        "Do not change any other repository file and do not use network tools."
    )
    env = {
        "HOME": str(args.artifact_root / "claude-home"),
        "LANG": "C.UTF-8",
        "PATH": str(executable.parent) + ":/usr/bin:/bin",
        "CLAUDE_CODE_OAUTH_TOKEN": _read_controller_secret(token_file),
        "TCF_RUNTIME_ROOT": str(args.runtime_root),
    }
    Path(env["HOME"]).mkdir(mode=0o700)
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=args.repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    observed = subprocess.run(
        [
            str(executable),
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            "2",
            "--allowedTools",
            "Write",
            "--disallowedTools",
            "Bash,WebFetch,WebSearch,Task,Skill",
        ],
        cwd=args.repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    artifact_bytes: bytes | None = None
    if workspace_output.exists() and not workspace_output.is_symlink():
        workspace_stat = workspace_output.stat(follow_symlinks=False)
        if stat.S_ISREG(workspace_stat.st_mode) and workspace_stat.st_nlink == 1:
            artifact_bytes = workspace_output.read_bytes()
        workspace_output.unlink()
    if artifact_bytes == b"TRAINCAPSULE_CLAUDE_CANARY_OK\n":
        output.write_bytes(artifact_bytes)
    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=args.repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    after_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=args.repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    after_tree = subprocess.run(
        ["git", "rev-parse", f"{args.main_sha}^{{tree}}"],
        cwd=args.repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    proven = (
        observed.returncode == 0
        and artifact_bytes == b"TRAINCAPSULE_CLAUDE_CANARY_OK\n"
        and output.is_file()
        and before == after
        and after_sha == args.main_sha
        and after_tree == args.tree_sha
    )
    return {
        "proven": proven,
        "backend": "claude-code-max-oauth",
        "returnCode": observed.returncode,
        "responseDigest": _digest(observed.stdout.encode()),
        "mechanicalArtifactDigest": _digest(output.read_bytes()) if output.is_file() else None,
        "repositoryUnchanged": before == after,
        "exactShaUnchanged": after_sha == args.main_sha,
        "exactTreeUnchanged": after_tree == args.tree_sha,
    }


def _github_revert(args: argparse.Namespace) -> dict[str, object]:
    config = _load_policy().github
    gh = Path(config.executable)
    repository = config.repository
    token_file = Path(config.token_file)
    _trusted_executable(gh, config.executable_digest)
    env = {
        "GH_TOKEN": _read_controller_secret(token_file),
        "GH_REPO": repository,
        "HOME": str(args.artifact_root),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    branch = f"canary/post-merge-{args.run_id.lower()}"
    revert_branch = f"canary/revert-{args.run_id.lower()}"
    probe = subprocess.run(
        [
            str(gh),
            "api",
            f"repos/{repository}/actions/runs",
            "--method",
            "GET",
            "-f",
            f"head_sha={args.main_sha}",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode != 0:
        raise ValueError("GitHub App cannot observe the isolated canary repository")
    # Mutation is delegated to a root-installed canary workflow; this client only dispatches
    # the exact SHA/tree request and verifies the resulting revert PR independently.
    dispatched = subprocess.run(
        [
            str(gh),
            "workflow",
            "run",
            config.workflow,
            "--repo",
            repository,
            "--ref",
            "main",
            "-f",
            f"exact_main_sha={args.main_sha}",
            "-f",
            f"exact_tree_sha={args.tree_sha}",
            "-f",
            f"candidate_branch={branch}",
            "-f",
            f"revert_branch={revert_branch}",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if dispatched.returncode != 0:
        raise ValueError("isolated revert canary workflow dispatch was rejected")
    verified_stdout = ""
    verified_returncode = 1
    for attempt in range(30):
        verified = subprocess.run(
            [
                str(gh),
                "pr",
                "list",
                "--repo",
                repository,
                "--head",
                revert_branch,
                "--state",
                "open",
                "--json",
                "number,headRefName,baseRefName,body,statusCheckRollup",
            ],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        verified_returncode = verified.returncode
        verified_stdout = verified.stdout
        if verified_returncode == 0:
            observed_rows: object = json.loads(verified_stdout)
            if isinstance(observed_rows, list) and observed_rows:
                break
        if attempt < 29:
            time.sleep(10)
    raw_rows: object = json.loads(verified_stdout) if verified_returncode == 0 else []
    rows = cast(list[object], raw_rows) if isinstance(raw_rows, list) else []
    row = cast(dict[str, object], rows[0]) if len(rows) == 1 and isinstance(rows[0], dict) else {}
    checks_raw = row.get("statusCheckRollup")
    checks = cast(list[object], checks_raw) if isinstance(checks_raw, list) else []
    conclusions = {
        cast(dict[str, object], item).get("conclusion")
        for item in checks
        if isinstance(item, dict)
    }
    body = row.get("body")
    required_body = (
        isinstance(body, str)
        and "TrainCapsule-Automated-Revert: true" in body
        and f"Exact-Main-SHA: {args.main_sha}" in body
        and f"Exact-Tree-SHA: {args.tree_sha}" in body
    )
    proven = (
        len(rows) == 1
        and row.get("headRefName") == revert_branch
        and row.get("baseRefName") == "main"
        and required_body
        and bool(checks)
        and conclusions == {"SUCCESS"}
    )
    return {
        "proven": proven,
        "repository": repository,
        "exactMainSha": args.main_sha,
        "exactTreeSha": args.tree_sha,
        "candidateBranch": branch,
        "revertBranch": revert_branch,
        "revertPrObservationDigest": _digest(verified_stdout.encode()),
    }


def run_probe(canary_id: str, args: argparse.Namespace) -> dict[str, object]:
    if canary_id == "real_claude_mechanical_task":
        return _claude(args)
    if canary_id == "post_merge_invariant_failure_and_automated_revert_pr":
        return _github_revert(args)
    raise ValueError("external canary identity is not recognized")
