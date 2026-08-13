"""Offline assembler for an exact privileged-installer input bundle.

Every authority-bearing input is supplied by path.  This module creates no keys,
credentials, receipts, PASS decisions, oracle outcomes, or network traffic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from traincapsule_verifier.bootstrap import production_install_manifest
from traincapsule_verifier.canonical import canonical_json_bytes

from .privileged_installer import (
    ANCHOR_FETCHER_USER,
    CANARY_DISTRIBUTION_FILES,
    CANARY_GITHUB_TOKEN_TARGET,
    CANARY_IDS,
    DEFAULT_CONTROLLER_USER,
    PATH_UNITS,
    ROLE_TARGETS,
    RULESET_USER,
    SELECTOR_USER,
    SERVICE_USER,
    TOKEN_REFRESHER_USER,
    FilePin,
    LockedAccount,
    PrivilegedInstallSpec,
    load_repository_snapshot_manifest,
    production_directory_pins,
    unsigned_manifest_digest,
    validate_repository_snapshot_archive,
)

SECRET_ROLES = frozenset(
    {
        "private-key",
        "github-app-private-key",
        "selector-private-key",
        "selector-credential",
        "ruleset-private-key",
        "ruleset-credential",
        "controller-oauth-token",
        "canary-claude-token",
        "github-token-refresher-private-key",
        "git-anchor-github-private-key",
        "git-anchor-observer-private-key",
    }
)
_ORACLE_NAME = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class BundleAssemblyError(RuntimeError):
    """A missing or unsafe externally provisioned bundle input."""


def _metadata(role: str) -> tuple[str, str, str]:
    if role == "public-verifier":
        return "root", "root", "0755"
    if role in {"issuer", "activation-issuer", "check-worker"}:
        return "root", SERVICE_USER, "0750"
    if role == "observed-main-selector":
        return "root", SELECTOR_USER, "0750"
    if role == "ruleset-observer":
        return "root", RULESET_USER, "0750"
    if role in {
        "receipt-broker",
        "request-broker",
        "activation-selector-broker",
        "activation-request-broker",
        "ruleset-broker",
        "controller-start-broker",
        "post-activation-observer",
        "git-anchor-updater",
    }:
        return "root", "root", "0700"
    if role in {"git-anchor-producer", "git-anchor-askpass"}:
        return "root", ANCHOR_FETCHER_USER, "0750"
    if role in {"git-anchor-github-private-key", "git-anchor-observer-private-key"}:
        return ANCHOR_FETCHER_USER, ANCHOR_FETCHER_USER, "0600"
    if role in {"git-anchor-producer-policy", "git-anchor-observer-public-key"}:
        return "root", "root", "0444"
    if role in {"private-key", "github-app-private-key"}:
        return SERVICE_USER, SERVICE_USER, "0600"
    if role in {"selector-private-key", "selector-credential"}:
        return SELECTOR_USER, SELECTOR_USER, "0600"
    if role in {"ruleset-private-key", "ruleset-credential"}:
        return RULESET_USER, RULESET_USER, "0600"
    if role == "activation-supervisor-launcher":
        return "root", DEFAULT_CONTROLLER_USER, "0750"
    if role == "github-token-refresher":
        return "root", TOKEN_REFRESHER_USER, "0750"
    if role == "github-token-refresher-private-key":
        return TOKEN_REFRESHER_USER, TOKEN_REFRESHER_USER, "0600"
    if role == "github-token-refresher-policy":
        return "root", "root", "0444"
    if role == "canary-policy":
        return "root", "root", "0444"
    if role == "canary-live-probes-policy" or role.startswith("canary-distribution-"):
        return "root", "root", "0444"
    if role == "python-runtime-manifest":
        return "root", "root", "0444"
    if role in {
        "installed-controller-runtime-manifest",
        "controller-package-manifest",
        "controller-dependency-lock",
        "controller-runtime-environment",
        "controller-effective-config",
        "repository-snapshot",
        "repository-snapshot-manifest",
    }:
        return "root", "root", "0444"
    if role.startswith("runtime-") and role.endswith("-wheel"):
        return "root", "root", "0444"
    if role == "controller-oauth-token":
        return DEFAULT_CONTROLLER_USER, DEFAULT_CONTROLLER_USER, "0600"
    if role == "canary-claude-token":
        return DEFAULT_CONTROLLER_USER, DEFAULT_CONTROLLER_USER, "0400"
    if role == "canary-runner" or role.startswith("canary-"):
        return "root", "root", "0555"
    if role == "python-runtime":
        return "root", "root", "0555"
    if role == "external-evidence-broker":
        return "root", "root", "0755"
    if role == "external-evidence-public-key":
        return "root", "root", "0444"
    if role.startswith("external-evidence-") and role not in {
        "external-evidence-service",
        "external-evidence-path",
    }:
        return "root", "root", "0400"
    return "root", "root", "0644"


def _safe_source(path: Path, *, secret: bool, executable: bool, repo_root: Path) -> Path:
    if not path.is_absolute():
        raise BundleAssemblyError("artifact paths must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise BundleAssemblyError("required pre-provisioned artifact is missing") from exc
    current = path
    while True:
        if current.is_symlink():
            raise BundleAssemblyError("symbolic links are forbidden in artifact paths")
        if current == current.parent:
            break
        current = current.parent
    metadata = resolved.stat()
    if (
        not resolved.is_file()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size == 0
        or metadata.st_size > 128_000_000
    ):
        raise BundleAssemblyError("artifacts must be regular files")
    if executable and not metadata.st_mode & 0o111:
        raise BundleAssemblyError("pre-built executable artifact is not executable")
    if secret and metadata.st_mode & 0o077:
        raise BundleAssemblyError("pre-provisioned secret input has an unsafe mode")
    if secret and resolved.is_relative_to(repo_root.resolve(strict=True)):
        raise BundleAssemblyError("secret inputs must be provisioned outside the repository")
    return resolved


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


def _validate_static_elf(path: Path) -> None:
    raw = path.read_bytes()
    if len(raw) < 64 or raw[:4] != b"\x7fELF" or raw[5] not in {1, 2}:
        raise BundleAssemblyError("Python runtime must be a self-contained ELF executable")
    byteorder = "little" if raw[5] == 1 else "big"
    if raw[4] == 2:
        program_offset = int.from_bytes(raw[32:40], byteorder)
        entry_size = int.from_bytes(raw[54:56], byteorder)
        entry_count = int.from_bytes(raw[56:58], byteorder)
    elif raw[4] == 1:
        program_offset = int.from_bytes(raw[28:32], byteorder)
        entry_size = int.from_bytes(raw[42:44], byteorder)
        entry_count = int.from_bytes(raw[44:46], byteorder)
    else:
        raise BundleAssemblyError("Python runtime ELF class is unsupported")
    if (
        entry_size < 4
        or entry_count == 0
        or entry_count > 4096
        or program_offset + entry_size * entry_count > len(raw)
    ):
        raise BundleAssemblyError("Python runtime ELF program table is invalid")
    for index in range(entry_count):
        offset = program_offset + index * entry_size
        if int.from_bytes(raw[offset : offset + 4], byteorder) == 3:
            raise BundleAssemblyError("Python runtime has an external dynamic loader")


def _validate_python_runtime(
    manifest_path: Path, runtime_path: Path, sources: Mapping[str, Path]
) -> None:
    try:
        parsed: object = json.loads(manifest_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleAssemblyError("Python runtime manifest is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BundleAssemblyError("Python runtime manifest contract is not exact")
    manifest = cast(dict[str, object], parsed)
    dependencies_raw = manifest.get("dependencies")
    applications_raw = manifest.get("applications")
    if (
        set(manifest)
        != {
            "schemaVersion",
            "pythonVersion",
            "executableDigest",
            "selfContained",
            "dependencies",
            "applications",
        }
        or manifest["schemaVersion"] != "3.1"
        or not isinstance(manifest["pythonVersion"], str)
        or not re.fullmatch(r"3\.12\.\d+", manifest["pythonVersion"])
        or manifest["executableDigest"] != _digest(runtime_path)
        or manifest["selfContained"] is not True
        or not isinstance(dependencies_raw, list)
        or not isinstance(applications_raw, list)
    ):
        raise BundleAssemblyError("Python runtime manifest contract is not exact")
    dependencies = cast(list[object], dependencies_raw)
    dependency_roles = {
        "pydantic": "runtime-pydantic-wheel",
        "pydantic-core": "runtime-pydantic-core-wheel",
        "typing-extensions": "runtime-typing-extensions-wheel",
        "typing-inspection": "runtime-typing-inspection-wheel",
        "cryptography": "runtime-cryptography-wheel",
        "cffi": "runtime-cffi-wheel",
        "pycparser": "runtime-pycparser-wheel",
    }
    required = set(dependency_roles)
    observed: set[str] = set()
    for raw_dependency in dependencies:
        if not isinstance(raw_dependency, dict):
            raise BundleAssemblyError("Python dependency lock entry is invalid")
        dependency = cast(dict[str, object], raw_dependency)
        if (
            set(dependency) != {"name", "version", "wheelDigest"}
            or not isinstance(dependency["name"], str)
            or not isinstance(dependency["version"], str)
            or not re.fullmatch(r"[A-Za-z0-9_.+-]+", dependency["version"])
            or not isinstance(dependency["wheelDigest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", dependency["wheelDigest"])
        ):
            raise BundleAssemblyError("Python dependency lock entry is invalid")
        name = dependency["name"].lower().replace("_", "-")
        if name in observed:
            raise BundleAssemblyError("Python dependency lock contains duplicates")
        if name not in dependency_roles or dependency["wheelDigest"] != _digest(
            sources[dependency_roles[name]]
        ):
            raise BundleAssemblyError("Python dependency wheel digest is inconsistent")
        observed.add(name)
    if observed != required:
        raise BundleAssemblyError("Python runtime lacks the pinned canary dependency closure")
    applications = cast(list[object], applications_raw)
    application_roles = {
        "verifier": "runtime-verifier-wheel",
        "controller": "runtime-controller-wheel",
        "deployment": "runtime-deployment-wheel",
        "canary-runner": "runtime-canary-wheel",
    }
    seen_applications: set[str] = set()
    for raw_application in applications:
        if not isinstance(raw_application, dict):
            raise BundleAssemblyError("Python application lock entry is invalid")
        application = cast(dict[str, object], raw_application)
        name = application.get("name")
        digest = application.get("wheelDigest")
        if (
            set(application) != {"name", "wheelDigest"}
            or not isinstance(name, str)
            or name not in application_roles
            or not isinstance(digest, str)
            or digest != _digest(sources[application_roles[name]])
            or name in seen_applications
        ):
            raise BundleAssemblyError("Python application wheel digest is inconsistent")
        seen_applications.add(name)
    if seen_applications != set(application_roles):
        raise BundleAssemblyError("Python runtime lacks an application distribution")
    _validate_static_elf(runtime_path)


def _validate_controller_runtime(sources: Mapping[str, Path]) -> None:
    raw = sources["installed-controller-runtime-manifest"].read_bytes()
    manifest = _canonical_mapping(raw, label="installed controller runtime manifest")
    expected_keys = {
        "schemaVersion",
        "manifestDigest",
        "controllerPrincipal",
        "serviceName",
        "distributionRoot",
        "repositoryRoot",
        "runtimeRoot",
        "pythonRuntime",
        "packageManifest",
        "dependencyLock",
        "controllerUnit",
        "environmentFile",
        "effectiveConfig",
        "repositorySnapshotManifest",
        "repositoryMainSha",
        "repositoryTreeSha",
        "mutableGitRoot",
        "mutableWorktreeRoot",
        "artifactRoot",
        "entryArguments",
    }
    if (
        set(manifest) != expected_keys
        or manifest["schemaVersion"] != "3.1"
        or manifest["controllerPrincipal"] != DEFAULT_CONTROLLER_USER
        or manifest["serviceName"] != "traincapsule-controller.service"
        or manifest["distributionRoot"] != "/opt/traincapsule-runtime"
        or manifest["repositoryRoot"]
        != "/var/lib/traincapsule-verifier/repository-boundary"
        or manifest["runtimeRoot"] != "/var/lib/traincapsule-runtime"
        or manifest["mutableGitRoot"] != "/var/lib/traincapsule-runtime/git"
        or manifest["mutableWorktreeRoot"] != "/var/lib/traincapsule-runtime/worktrees"
        or manifest["artifactRoot"] != "/var/lib/traincapsule-runtime/artifacts/v3"
        or manifest["entryArguments"]
        != [
            "-m",
            "tcfactory",
            "v3-controller",
            "--repo",
            "/var/lib/traincapsule-verifier/repository-boundary",
        ]
    ):
        raise BundleAssemblyError("installed controller runtime contract is not exact")
    zeroed = dict(manifest)
    zeroed["manifestDigest"] = "sha256:" + "0" * 64
    if manifest["manifestDigest"] != "sha256:" + hashlib.sha256(
        canonical_json_bytes(zeroed)
    ).hexdigest():
        raise BundleAssemblyError("installed controller runtime manifest digest is invalid")
    artifact_roles = {
        "pythonRuntime": ("python-runtime", True),
        "packageManifest": ("controller-package-manifest", False),
        "dependencyLock": ("controller-dependency-lock", False),
        "controllerUnit": ("controller-service", False),
        "environmentFile": ("controller-runtime-environment", False),
        "effectiveConfig": ("controller-effective-config", False),
        "repositorySnapshotManifest": ("repository-snapshot-manifest", False),
    }
    for field, (role, executable) in artifact_roles.items():
        artifact = manifest[field]
        if not isinstance(artifact, dict) or artifact != {
            "path": ROLE_TARGETS[role],
            "digest": _digest(sources[role]),
            "executable": executable,
        }:
            raise BundleAssemblyError("installed controller artifact pin is inconsistent")
    snapshot = load_repository_snapshot_manifest(sources["repository-snapshot-manifest"])
    if (
        manifest["repositoryMainSha"] != snapshot.main_sha
        or manifest["repositoryTreeSha"] != snapshot.tree_sha
    ):
        raise BundleAssemblyError("installed controller repository identity is inconsistent")

    unit_lines = sources["controller-service"].read_text(encoding="utf-8").splitlines()
    arguments = (
        "-m tcfactory v3-controller --repo "
        "/var/lib/traincapsule-verifier/repository-boundary"
    )
    required = {
        "[Service]",
        f"User={DEFAULT_CONTROLLER_USER}",
        f"Group={DEFAULT_CONTROLLER_USER}",
        f"ExecStart={ROLE_TARGETS['python-runtime']} {arguments}",
        f"EnvironmentFile={ROLE_TARGETS['controller-runtime-environment']}",
        "WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary",
        "NoNewPrivileges=yes",
    }
    if (
        not required <= set(unit_lines)
        or sum(line.startswith("ExecStart=") for line in unit_lines) != 1
        or sum(line.startswith("User=") for line in unit_lines) != 1
        or sum(line.startswith("Group=") for line in unit_lines) != 1
    ):
        raise BundleAssemblyError("controller service does not bind the installed runtime")
    environment = sources["controller-runtime-environment"].read_bytes()
    forbidden_environment = (
        b"/home/",
        b"/.cache/",
        b"uv run",
        b"ANTHROPIC_API_KEY",
        b"OPENAI_API_KEY",
        b"ANTHROPIC_AUTH_TOKEN",
        b"CLAUDE_CODE_OAUTH_TOKEN",
        b"GITHUB_TOKEN=",
        b"GH_TOKEN=",
        b"sk-ant-",
    )
    if any(value in environment for value in forbidden_environment):
        raise BundleAssemblyError("controller environment contains a forbidden runtime or key")
    if (
        environment.count(b"TCF_RUNTIME_ROOT=/var/lib/traincapsule-runtime\n") != 1
        or b"TRAINCAPSULE_RUNTIME_ROOT=" in environment
    ):
        raise BundleAssemblyError("controller environment does not bind the installed runtime root")


def _validate_interpreters(sources: Mapping[str, Path]) -> None:
    expected = b"#!/opt/traincapsule-runtime/bin/python3.12"
    forbidden = (
        b"/home/",
        b"/usr/bin/env python",
        b"/.cache/",
        b"/uv/",
        b"uv run",
        b"BASH_SOURCE",
    )
    for role, source in sources.items():
        _, _, mode = _metadata(role)
        if not int(mode, 8) & 0o111 or role == "python-runtime":
            continue
        prefix = source.read_bytes()[:512]
        if any(value in prefix for value in forbidden):
            raise BundleAssemblyError("executable interpreter resolves into an unsafe runtime")
        if prefix.startswith(b"\x7fELF"):
            continue
        if not prefix.startswith(b"#!") or not (
            prefix.startswith(expected + b"\n")
            or prefix.startswith(b"#!/bin/bash\n")
            or prefix.startswith(b"#!/bin/sh\n")
            or prefix.startswith(b"#!/usr/bin/env bash\n")
        ):
            raise BundleAssemblyError("executable uses an unpinned interpreter")


def _validate_canary_policy(policy_path: Path, sources: Mapping[str, Path]) -> None:
    try:
        parsed: object = json.loads(policy_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleAssemblyError("canary policy is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BundleAssemblyError("canary policy top-level contract is not exact")
    payload = cast(dict[str, object], parsed)
    if set(payload) != {
        "schemaVersion",
        "runnerExecutableDigest",
        "distributionDigest",
        "mechanisms",
    }:
        raise BundleAssemblyError("canary policy top-level contract is not exact")
    if payload["schemaVersion"] != "3.1" or payload["runnerExecutableDigest"] != _digest(
        sources["canary-runner"]
    ):
        raise BundleAssemblyError("canary runner digest is not pinned by its policy")
    distribution = hashlib.sha256()
    for name in sorted(CANARY_DISTRIBUTION_FILES):
        role = f"canary-distribution-{name[:-3].replace('_', '-')}"
        relative = name.encode()
        content = sources[role].read_bytes()
        distribution.update(len(relative).to_bytes(4, "big"))
        distribution.update(relative)
        distribution.update(len(content).to_bytes(8, "big"))
        distribution.update(content)
    if payload["distributionDigest"] != "sha256:" + distribution.hexdigest():
        raise BundleAssemblyError("canary distribution digest is not pinned by its policy")
    mechanisms_raw = payload["mechanisms"]
    if not isinstance(mechanisms_raw, dict):
        raise BundleAssemblyError("canary policy must pin exactly all 20 mechanisms")
    mechanisms = cast(dict[str, object], mechanisms_raw)
    if set(mechanisms) != set(CANARY_IDS):
        raise BundleAssemblyError("canary policy must pin exactly all 20 mechanisms")
    network_canaries = {
        "real_claude_mechanical_task",
        "post_merge_invariant_failure_and_automated_revert_pr",
    }
    for canary_id in CANARY_IDS:
        mechanism_raw = mechanisms[canary_id]
        role = f"canary-{canary_id}"
        if not isinstance(mechanism_raw, dict):
            raise BundleAssemblyError("canary mechanism policy contract is not exact")
        mechanism = cast(dict[str, object], mechanism_raw)
        if set(mechanism) != {
            "executable",
            "executableDigest",
            "timeoutSeconds",
            "networkAllowed",
        }:
            raise BundleAssemblyError("canary mechanism policy contract is not exact")
        timeout = mechanism["timeoutSeconds"]
        if (
            mechanism["executable"] != ROLE_TARGETS[role]
            or mechanism["executableDigest"] != _digest(sources[role])
            or type(timeout) is not int
            or not 1 <= timeout <= 14_400
            or mechanism["networkAllowed"] is not (canary_id in network_canaries)
        ):
            raise BundleAssemblyError("canary mechanism policy pin is inconsistent")


def _validate_live_canary_policy(path: Path, sources: Mapping[str, Path]) -> None:
    try:
        parsed: object = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleAssemblyError("live canary policy is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BundleAssemblyError("live canary policy contract is not exact")
    policy = cast(dict[str, object], parsed)
    if set(policy) != {"schemaVersion", "claude", "github"} or policy["schemaVersion"] != "3.1":
        raise BundleAssemblyError("live canary policy contract is not exact")
    claude_raw = policy["claude"]
    github_raw = policy["github"]
    if not isinstance(claude_raw, dict) or not isinstance(github_raw, dict):
        raise BundleAssemblyError("live canary policy probes are not exact")
    claude = cast(dict[str, object], claude_raw)
    github = cast(dict[str, object], github_raw)
    if (
        set(claude) != {"executable", "executableDigest", "tokenFile"}
        or claude["executable"] != ROLE_TARGETS["canary-claude-executable"]
        or claude["executableDigest"] != _digest(sources["canary-claude-executable"])
        or claude["tokenFile"] != ROLE_TARGETS["canary-claude-token"]
        or set(github)
        != {
            "executable",
            "executableDigest",
            "tokenFile",
            "repository",
            "workflow",
        }
        or github["executable"] != ROLE_TARGETS["canary-github-executable"]
        or github["executableDigest"] != _digest(sources["canary-github-executable"])
        or github["tokenFile"] != CANARY_GITHUB_TOKEN_TARGET
        or not isinstance(github["repository"], str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", github["repository"])
        or github["workflow"] != "traincapsule-post-merge-revert-canary.yml"
    ):
        raise BundleAssemblyError("live canary policy executable or credential pin is unsafe")


def _validate_controller_oauth(path: Path) -> None:
    raw = path.read_bytes()
    if (
        not 32 <= len(raw) <= 4096
        or b"\x00" in raw
        or b"\r" in raw
        or b"\n" in raw
        or not raw.startswith(b"sk-ant-oat01-")
    ):
        raise BundleAssemblyError("controller credential is not a Claude Max OAuth token")
    expected_suffix = Path(".config/traincapsule/claude-oauth-token").parts
    if path.parts[-len(expected_suffix) :] != expected_suffix:
        raise BundleAssemblyError("controller OAuth token source path is not the fixed WSL path")


def _validate_github_token_refresher(sources: Mapping[str, Path]) -> None:
    policy = _canonical_mapping(
        sources["github-token-refresher-policy"].read_bytes(),
        label="GitHub token refresher policy",
    )
    expected = {
        "schemaVersion",
        "githubAppId",
        "installationId",
        "repository",
        "audience",
        "permissions",
        "privateKeyPath",
        "outboxTokenPath",
        "outboxMetadataPath",
        "targetTokenPath",
        "targetMetadataPath",
        "refreshBeforeSeconds",
    }
    if (
        set(policy) != expected
        or policy["schemaVersion"] != "3.1"
        or type(policy["githubAppId"]) is not int
        or policy["githubAppId"] <= 0
        or type(policy["installationId"]) is not int
        or policy["installationId"] <= 0
        or not isinstance(policy["repository"], str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", policy["repository"])
        or policy["audience"] != "https://api.github.com"
        or policy["permissions"] != {"actions": "write", "contents": "read"}
        or policy["privateKeyPath"] != ROLE_TARGETS["github-token-refresher-private-key"]
        or policy["outboxTokenPath"] != "/var/lib/traincapsule-github-token/outbox/token"
        or policy["outboxMetadataPath"]
        != "/var/lib/traincapsule-github-token/outbox/token-metadata.json"
        or policy["targetTokenPath"] != CANARY_GITHUB_TOKEN_TARGET
        or policy["targetMetadataPath"]
        != "/var/lib/traincapsule-canary-secrets/github-app-installation-token.json"
        or type(policy["refreshBeforeSeconds"]) is not int
        or not 300 <= policy["refreshBeforeSeconds"] <= 1800
    ):
        raise BundleAssemblyError("GitHub token refresher policy is unsafe")
    try:
        key = serialization.load_pem_private_key(
            sources["github-token-refresher-private-key"].read_bytes(), password=None
        )
    except ValueError as exc:
        raise BundleAssemblyError("GitHub token refresher private key is invalid") from exc
    if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
        raise BundleAssemblyError("GitHub token refresher key must be RSA-2048 or stronger")


def _validate_anchor_producer(sources: Mapping[str, Path]) -> None:
    policy = _canonical_mapping(
        sources["git-anchor-producer-policy"].read_bytes(),
        label="Git anchor producer policy",
    )
    required_checks = {
        "TrainCapsule / Factory quality",
        "TrainCapsule / Product unit",
        "TrainCapsule / Product contract",
        "TrainCapsule / Security",
        "TrainCapsule / Source-of-truth integrity",
        "TrainCapsule / Packaging install",
        "TrainCapsule / Docs and schemas",
        "TrainCapsule / Source freshness",
        "TrainCapsule / Machine policy",
    }
    raw_check_ids = policy.get("requiredCheckAppIds")
    if not isinstance(raw_check_ids, dict):
        raise BundleAssemblyError("Git anchor producer policy is unsafe")
    check_ids = cast(dict[str, object], raw_check_ids)
    anchor_policy = _canonical_mapping(
        sources["git-anchor-policy"].read_bytes(), label="Git anchor updater policy"
    )
    snapshot = load_repository_snapshot_manifest(sources["repository-snapshot-manifest"])
    if (
        set(policy)
        != {
            "schemaVersion",
            "repository",
            "githubAppId",
            "installationId",
            "permissions",
            "requiredCheckAppIds",
            "sourceGenerationId",
            "sourceGenerationDigest",
            "privateKeyPath",
            "observerKeyPath",
            "rulesetReceiptPath",
            "rulesetPublicKeyPath",
        }
        or policy["schemaVersion"] != "3.1"
        or policy["repository"] != "TasfiqJ/TrainCapsule"
        or type(policy["githubAppId"]) is not int
        or policy["githubAppId"] <= 0
        or type(policy["installationId"]) is not int
        or policy["installationId"] <= 0
        or policy["permissions"]
        != {"checks": "read", "contents": "read", "pull_requests": "read"}
        or set(check_ids) != required_checks
        or any(type(value) is not int or value <= 0 for value in check_ids.values())
        or policy["privateKeyPath"] != ROLE_TARGETS["git-anchor-github-private-key"]
        or policy["observerKeyPath"] != ROLE_TARGETS["git-anchor-observer-private-key"]
        or policy["rulesetReceiptPath"] != "/var/lib/traincapsule-verifier/ruleset/current.json"
        or policy["rulesetPublicKeyPath"] != ROLE_TARGETS["ruleset-public-key"]
        or set(anchor_policy)
        != {
            "schemaVersion",
            "repository",
            "sourceGenerationId",
            "sourceGenerationDigest",
            "anchorRoot",
            "transactionRoot",
        }
        or anchor_policy["schemaVersion"] != "3.1"
        or anchor_policy["repository"] != "TasfiqJ/TrainCapsule"
        or anchor_policy["anchorRoot"] != "/var/lib/traincapsule-runtime/git"
        or anchor_policy["transactionRoot"]
        != "/var/lib/traincapsule-verifier/anchor-update-journal"
        or policy["sourceGenerationId"] != anchor_policy.get("sourceGenerationId")
        or policy["sourceGenerationDigest"] != anchor_policy.get("sourceGenerationDigest")
        or policy["sourceGenerationDigest"] != snapshot.source_generation_digest
    ):
        raise BundleAssemblyError("Git anchor producer policy is unsafe")
    try:
        github_key = serialization.load_pem_private_key(
            sources["git-anchor-github-private-key"].read_bytes(), password=None
        )
        observer_key = serialization.load_pem_private_key(
            sources["git-anchor-observer-private-key"].read_bytes(), password=None
        )
        observer_public = serialization.load_pem_public_key(
            sources["git-anchor-observer-public-key"].read_bytes()
        )
    except ValueError as exc:
        raise BundleAssemblyError("Git anchor producer key material is invalid") from exc
    if not isinstance(github_key, RSAPrivateKey) or github_key.key_size < 2048:
        raise BundleAssemblyError("Git anchor App key must be RSA-2048 or stronger")
    if (
        not isinstance(observer_key, Ed25519PrivateKey)
        or not isinstance(observer_public, Ed25519PublicKey)
        or observer_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        != observer_public.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ):
        raise BundleAssemblyError("Git anchor observer key pair does not match")


def _validate_repository_git_graph(
    archive_path: Path, manifest_path: Path
) -> None:
    manifest = load_repository_snapshot_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix="traincapsule-snapshot-preflight-") as raw_root:
        root = Path(raw_root)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest.entries:
                target = root.joinpath(*PurePosixPath(entry.path).parts)
                if entry.kind == "directory":
                    target.mkdir(mode=0o700, parents=False)
                else:
                    target.write_bytes(archive.read(entry.path))
        commands = (
            (("fsck", "--strict", "--no-dangling"), None),
            (("remote",), ""),
            (("rev-parse", "HEAD"), manifest.main_sha),
            (("rev-parse", "HEAD^{tree}"), manifest.tree_sha),
            (("status", "--porcelain=v1", "--untracked-files=all"), ""),
        )
        for arguments, expected in commands:
            result = subprocess.run(
                ["/usr/bin/git", "-C", str(root), *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                env={
                    "PATH": "/usr/bin:/bin",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_SYSTEM": "/dev/null",
                },
            )
            if result.returncode != 0 or (
                expected is not None and result.stdout.strip() != expected
            ):
                raise BundleAssemblyError("repository snapshot Git graph is inconsistent")


def _canonical_mapping(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleAssemblyError(f"{label} is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BundleAssemblyError(f"{label} is not an object")
    value = cast(dict[str, object], parsed)
    if canonical_json_bytes(value) != raw:
        raise BundleAssemblyError(f"{label} is not canonical JSON")
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise BundleAssemblyError(f"{label} expiry is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BundleAssemblyError(f"{label} expiry is invalid") from exc
    if result.tzinfo is None:
        raise BundleAssemblyError(f"{label} expiry is invalid")
    return result


def _validate_external_authority(sources: Mapping[str, Path]) -> None:
    key_raw = sources["external-evidence-public-key"].read_bytes()
    try:
        public_key = serialization.load_pem_public_key(key_raw)
    except ValueError as exc:
        raise BundleAssemblyError("external-evidence authority key is invalid") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise BundleAssemblyError("external-evidence authority key is not Ed25519")
    revocation_raw = sources["external-evidence-revocations"].read_bytes()
    anchor_raw = sources["external-evidence-authority-anchor"].read_bytes()
    try:
        public_key.verify(
            sources["external-evidence-revocations-signature"].read_bytes(),
            revocation_raw,
        )
        public_key.verify(
            sources["external-evidence-authority-anchor-signature"].read_bytes(),
            anchor_raw,
        )
    except InvalidSignature as exc:
        raise BundleAssemblyError("external-evidence snapshot signature is invalid") from exc
    revocations = _canonical_mapping(revocation_raw, label="external-evidence revocation list")
    anchor = _canonical_mapping(anchor_raw, label="external-evidence authority anchor")
    revocation_keys = {
        "revocationVersion",
        "authorityId",
        "issuerId",
        "keyId",
        "epoch",
        "previousListDigest",
        "issuedAt",
        "expiresAt",
        "revokedReceiptIds",
        "revokedNonces",
    }
    anchor_keys = {
        "anchorVersion",
        "authorityId",
        "issuerId",
        "keyId",
        "epoch",
        "currentRevocationDigest",
        "previousRevocationDigest",
        "issuedAt",
        "expiresAt",
    }
    if set(revocations) != revocation_keys or set(anchor) != anchor_keys:
        raise BundleAssemblyError("external-evidence snapshot contract is not exact")
    if (
        revocations["revocationVersion"] != 1
        or anchor["anchorVersion"] != 1
        or revocations["epoch"] != 1
        or anchor["epoch"] != 1
        or revocations["previousListDigest"] is not None
        or anchor["previousRevocationDigest"] is not None
        or any(
            revocations[field] != anchor[field]
            for field in ("authorityId", "issuerId", "keyId", "epoch")
        )
        or anchor["currentRevocationDigest"] != _digest(sources["external-evidence-revocations"])
        or _timestamp(revocations["expiresAt"], label="revocation list") <= datetime.now(UTC)
        or _timestamp(anchor["expiresAt"], label="authority anchor") <= datetime.now(UTC)
    ):
        raise BundleAssemblyError("external-evidence epoch-1 snapshot is inconsistent or stale")


def assemble_bundle(
    destination: Path,
    *,
    artifacts: Mapping[str, Path],
    oracles: Mapping[str, Path],
    repo_root: Path,
) -> PrivilegedInstallSpec:
    """Atomically stage an exact inert bundle from externally supplied files."""

    if destination.exists() or destination.is_symlink():
        raise BundleAssemblyError("staging destination must be absent")
    missing = sorted(set(ROLE_TARGETS) - set(artifacts))
    extra = sorted(set(artifacts) - set(ROLE_TARGETS))
    if missing or extra:
        raise BundleAssemblyError(f"core artifact set mismatch; missing={missing}; extra={extra}")
    if not oracles:
        raise BundleAssemblyError("at least one pre-provisioned oracle runner is required")
    if any(not _ORACLE_NAME.fullmatch(name) for name in oracles):
        raise BundleAssemblyError("oracle names must be normalized lowercase identifiers")

    sources: dict[str, Path] = {}
    identities: dict[tuple[int, int], str] = {}
    for role in sorted(ROLE_TARGETS):
        _, _, mode = _metadata(role)
        source = _safe_source(
            artifacts[role],
            secret=role in SECRET_ROLES,
            executable=bool(int(mode, 8) & 0o111),
            repo_root=repo_root,
        )
        identity = (source.stat().st_dev, source.stat().st_ino)
        prior_role = identities.get(identity)
        oauth_alias = {prior_role, role} == {
            "controller-oauth-token",
            "canary-claude-token",
        }
        if prior_role is not None and not oauth_alias:
            raise BundleAssemblyError("duplicate artifact source or inode is forbidden")
        identities[identity] = role
        sources[role] = source
    for name in sorted(oracles):
        source = _safe_source(oracles[name], secret=False, executable=True, repo_root=repo_root)
        identity = (source.stat().st_dev, source.stat().st_ino)
        if identity in identities:
            raise BundleAssemblyError("duplicate artifact source or inode is forbidden")
        identities[identity] = f"oracle:{name}"
        sources[f"oracle:{name}"] = source

    _validate_interpreters(sources)
    pinned = {item.path: item.content_digest for item in production_install_manifest().files}
    for role, target in ROLE_TARGETS.items():
        if (
            target in pinned
            and role not in {"git-anchor-policy", "git-anchor-producer-policy"}
            and _digest(sources[role]) != pinned[target]
        ):
            raise BundleAssemblyError(f"repository-pinned artifact mismatch for role {role}")
    _validate_canary_policy(sources["canary-policy"], sources)
    _validate_live_canary_policy(sources["canary-live-probes-policy"], sources)
    _validate_python_runtime(sources["python-runtime-manifest"], sources["python-runtime"], sources)
    snapshot_manifest = load_repository_snapshot_manifest(
        sources["repository-snapshot-manifest"]
    )
    validate_repository_snapshot_archive(sources["repository-snapshot"], snapshot_manifest)
    _validate_repository_git_graph(
        sources["repository-snapshot"], sources["repository-snapshot-manifest"]
    )
    if (
        snapshot_manifest.effective_config_digest
        != _digest(sources["controller-effective-config"])
        or snapshot_manifest.python_runtime_manifest_digest
        != _digest(sources["python-runtime-manifest"])
        or snapshot_manifest.package_manifest_digest
        != _digest(sources["controller-package-manifest"])
        or snapshot_manifest.dependency_lock_digest
        != _digest(sources["controller-dependency-lock"])
    ):
        raise BundleAssemblyError("repository snapshot deployment binding is inconsistent")
    _validate_controller_runtime(sources)
    _validate_github_token_refresher(sources)
    _validate_anchor_producer(sources)
    _validate_controller_oauth(sources["controller-oauth-token"])
    if _digest(sources["canary-claude-token"]) != _digest(sources["controller-oauth-token"]):
        raise BundleAssemblyError("live Claude probe must use the provisioned Max OAuth token")
    _validate_external_authority(sources)
    repository_pins = {
        "activation-supervisor-launcher": repo_root / "scripts/windows_activation_entrypoint.sh",
        "external-evidence-service": (
            repo_root / "config/traincapsule-external-evidence-authority.service"
        ),
        "external-evidence-path": (
            repo_root / "config/traincapsule-external-evidence-authority.path"
        ),
        "github-token-refresher-service": (
            repo_root / "config/traincapsule-github-token-refresher.service"
        ),
        "github-token-refresher-timer": (
            repo_root / "config/traincapsule-github-token-refresher.timer"
        ),
        "github-token-promoter-service": (
            repo_root / "config/traincapsule-github-token-promoter.service"
        ),
        "github-token-promoter-path": (
            repo_root / "config/traincapsule-github-token-promoter.path"
        ),
    }
    repository_pins.update(
        {
            f"canary-distribution-{name[:-3].replace('_', '-')}": (
                repo_root / "canary_runner/src/traincapsule_canary_runner" / name
            )
            for name in CANARY_DISTRIBUTION_FILES
        }
    )
    for role, repository_path in repository_pins.items():
        if _digest(sources[role]) != _digest(repository_path.resolve(strict=True)):
            raise BundleAssemblyError(f"repository-pinned artifact mismatch for role {role}")

    service = LockedAccount(
        name=SERVICE_USER,
        home="/var/lib/traincapsule-verifier",
        shell="/usr/sbin/nologin",
    )
    selector = LockedAccount(
        name=SELECTOR_USER,
        home="/var/lib/traincapsule-verifier/selector-private",
        shell="/usr/sbin/nologin",
    )
    ruleset = LockedAccount(
        name=RULESET_USER,
        home="/var/lib/traincapsule-verifier/ruleset-private",
        shell="/usr/sbin/nologin",
    )
    token_refresher = LockedAccount(
        name=TOKEN_REFRESHER_USER,
        home="/var/lib/traincapsule-github-token",
        shell="/usr/sbin/nologin",
    )
    anchor_fetcher = LockedAccount(
        name=ANCHOR_FETCHER_USER,
        home="/var/lib/traincapsule-verifier/anchor-fetcher-private",
        shell="/usr/sbin/nologin",
    )
    controller = LockedAccount(
        name=DEFAULT_CONTROLLER_USER,
        home="/var/lib/traincapsule-controller",
        shell="/usr/sbin/nologin",
    )
    files: list[FilePin] = []
    for role in sorted(ROLE_TARGETS):
        owner, group, mode = _metadata(role)
        files.append(
            FilePin(
                role=role,
                source=f"payload/{role}",
                target=ROLE_TARGETS[role],
                sha256=_digest(sources[role]),
                owner=owner,
                group=group,
                mode=mode,
            )
        )
    for name in sorted(oracles):
        role = "oracle-" + hashlib.sha256(name.encode()).hexdigest()[:16]
        files.append(
            FilePin(
                role=role,
                source=f"payload/{role}",
                target=f"/var/lib/traincapsule-verifier/oracle/{name}",
                sha256=_digest(sources[f"oracle:{name}"]),
                owner=SERVICE_USER,
                group=SERVICE_USER,
                mode="0500",
            )
        )
        sources[role] = sources[f"oracle:{name}"]
    provisional: dict[str, object] = {
        "schemaVersion": "3.1",
        "state": "STAGED_NOT_INSTALLED",
        "manifestDigest": "sha256:" + "0" * 64,
        "serviceAccount": service.model_dump(mode="json", by_alias=True),
        "selectorAccount": selector.model_dump(mode="json", by_alias=True),
        "rulesetAccount": ruleset.model_dump(mode="json", by_alias=True),
        "tokenRefresherAccount": token_refresher.model_dump(mode="json", by_alias=True),
        "anchorFetcherAccount": anchor_fetcher.model_dump(mode="json", by_alias=True),
        "controllerAccount": controller.model_dump(mode="json", by_alias=True),
        "directories": [
            item.model_dump(mode="json", by_alias=True)
            for item in production_directory_pins(
                service_account=service,
                selector_account=selector,
                ruleset_account=ruleset,
                token_refresher_account=token_refresher,
                anchor_fetcher_account=anchor_fetcher,
                controller_account=controller,
            )
        ],
        "files": [item.model_dump(mode="json", by_alias=True) for item in files],
        "controllerUnit": "traincapsule-controller.service",
        "pathUnits": list(PATH_UNITS),
        "generatesCredentials": False,
        "generatesReceipts": False,
        "runsOracles": False,
    }
    provisional["manifestDigest"] = unsigned_manifest_digest(provisional)
    spec = PrivilegedInstallSpec.model_validate(provisional)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".traincapsule-bundle-", dir=destination.parent))
    try:
        os.chmod(temporary, 0o700)
        payload = temporary / "payload"
        payload.mkdir(mode=0o700)
        for item in files:
            target = payload / item.role
            shutil.copyfile(sources[item.role], target, follow_symlinks=False)
            target.chmod(0o600)
        manifest = temporary / "installer-manifest.json"
        manifest.write_bytes(canonical_json_bytes(spec))
        manifest.chmod(0o600)
        os.rename(temporary, destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return spec


def _assignments(values: Sequence[str], *, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or name in result:
            raise BundleAssemblyError(f"{label} values must be unique NAME=/absolute/path")
        result[name] = Path(raw_path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-assemble-production-bundle")
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--oracle", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        spec = assemble_bundle(
            args.stage,
            artifacts=_assignments(args.artifact, label="artifact"),
            oracles=_assignments(args.oracle, label="oracle"),
            repo_root=args.repo_root,
        )
    except (BundleAssemblyError, OSError, ValueError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "state": spec.state,
                "manifestDigest": spec.manifest_digest,
                "stage": str(args.stage),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
