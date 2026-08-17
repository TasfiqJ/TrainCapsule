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


def _github_direct_revert(args: argparse.Namespace) -> dict[str, object]:
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
    base = subprocess.run(
        [
            str(gh),
            "api",
            f"repos/{repository}/git/ref/heads/main",
            "--jq",
            ".object.sha",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    base_sha = base.stdout.strip()
    if base.returncode != 0 or len(base_sha) != 40:
        raise ValueError("isolated canary main identity is unavailable")
    base_tree_observation = subprocess.run(
        [
            str(gh),
            "api",
            f"repos/{repository}/git/commits/{base_sha}",
            "--jq",
            ".tree.sha",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    base_tree = base_tree_observation.stdout.strip()
    if base_tree_observation.returncode != 0 or len(base_tree) != 40:
        raise ValueError("isolated canary main tree is unavailable")
    # Mutation is delegated to the isolated repository workflow. It performs two ordinary,
    # non-force pushes to main: the intentional failure and its exact revert.
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
    observed_head = ""
    observed_tree = ""
    proven = False
    for attempt in range(30):
        head = subprocess.run(
            [
                str(gh),
                "api",
                f"repos/{repository}/git/ref/heads/main",
                "--jq",
                ".object.sha",
            ],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        observed_head = head.stdout.strip()
        if head.returncode == 0 and observed_head != base_sha and len(observed_head) == 40:
            tree = subprocess.run(
                [
                    str(gh),
                    "api",
                    f"repos/{repository}/git/commits/{observed_head}",
                    "--jq",
                    ".tree.sha",
                ],
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            observed_tree = tree.stdout.strip()
            checks = subprocess.run(
                [
                    str(gh),
                    "api",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{repository}/commits/{observed_head}/check-runs",
                ],
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            verified_stdout = checks.stdout
            if checks.returncode == 0:
                payload: object = json.loads(verified_stdout)
                typed_payload = (
                    cast(dict[str, object], payload) if isinstance(payload, dict) else {}
                )
                rows_raw = typed_payload.get("check_runs")
                rows = cast(list[object], rows_raw) if isinstance(rows_raw, list) else []
                matches = [
                    cast(dict[str, object], row)
                    for row in rows
                    if isinstance(row, dict)
                    and cast(dict[str, object], row).get("name")
                    == "TrainCapsule direct-main revert validation"
                    and cast(dict[str, object], row).get("conclusion") == "success"
                ]
                output = matches[0].get("output") if len(matches) == 1 else None
                summary = (
                    cast(dict[str, object], output).get("summary")
                    if isinstance(output, dict)
                    else None
                )
                proven = (
                    tree.returncode == 0
                    and observed_tree == base_tree
                    and isinstance(summary, str)
                    and "TrainCapsule-Direct-Main-Revert: true" in summary
                    and f"Exact-Main-SHA: {args.main_sha}" in summary
                    and f"Exact-Tree-SHA: {args.tree_sha}" in summary
                    and f"Canary-Base-SHA: {base_sha}" in summary
                    and f"Canary-Base-Tree: {base_tree}" in summary
                )
                if proven:
                    break
        if attempt < 29:
            time.sleep(10)
    return {
        "proven": proven,
        "repository": repository,
        "exactMainSha": args.main_sha,
        "exactTreeSha": args.tree_sha,
        "canaryBaseSha": base_sha,
        "canaryBaseTree": base_tree,
        "directRevertSha": observed_head,
        "restoredTree": observed_tree,
        "directRevertObservationDigest": _digest(verified_stdout.encode()),
    }


def run_probe(canary_id: str, args: argparse.Namespace) -> dict[str, object]:
    if canary_id == "real_claude_mechanical_task":
        return _claude(args)
    if canary_id == "post_push_invariant_failure_and_automatic_direct_revert":
        return _github_direct_revert(args)
    raise ValueError("external canary identity is not recognized")
