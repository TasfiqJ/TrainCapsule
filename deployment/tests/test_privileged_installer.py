from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import subprocess
import zipfile
import zlib
from pathlib import Path
from typing import NoReturn, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from traincapsule_verifier.bootstrap import (
    controller_start_policy_content,
    git_anchor_policy_content,
    git_anchor_producer_policy_content,
    post_activation_policy_content,
    render_systemd_units,
)
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest

from deployment.bundle_assembler import BundleAssemblyError, assemble_bundle, main
from deployment.privileged_installer import (
    APPLY_CONFIRMATION,
    CANARY_GITHUB_TOKEN_TARGET,
    CANARY_IDS,
    INITIAL_CONTROLLER_PYTHONPATH,
    PATH_UNITS,
    ROLE_TARGETS,
    DeploymentAttestation,
    InstallFailure,
    InstallPreview,
    LockedAccount,
    PrivilegedInstaller,
    PrivilegedInstallSpec,
    unsigned_manifest_digest,
)
from deployment.runtime_distribution import (
    COMPLETE_RUNTIME_IMPORTS,
    PROJECT_SOURCE_MAPPINGS,
    build_runtime_distribution,
)


class Crash(BaseException):
    pass


class FakeAuthority:
    simulated = True

    def __init__(self) -> None:
        self.ids = {
            "root": (0, 0),
            "traincapsule-verifier": (210, 210),
            "traincapsule-selector": (215, 215),
            "traincapsule-ruleset-observer": (218, 218),
            "traincapsule-github-token": (219, 219),
            "traincapsule-anchor-fetcher": (221, 221),
            "traincapsule-controller": (220, 220),
        }
        self.memberships = {name: {values[1]} for name, values in self.ids.items()}
        self.owners: dict[Path, tuple[int, int]] = {}
        self.accounts: set[str] = set()
        self.unsafe: set[str] = set()

    def ensure_locked(self, account: LockedAccount) -> bool:
        if account.name in self.unsafe:
            raise InstallFailure("existing account is unsafe")
        created = account.name not in self.accounts
        self.accounts.add(account.name)
        return created

    def uid(self, name: str) -> int:
        return self.ids[name][0]

    def gid(self, name: str) -> int:
        return self.ids[name][1]

    def groups(self, name: str) -> set[int]:
        return set(self.memberships[name])

    def owner(self, path: Path) -> tuple[int, int]:
        return self.owners.get(path, (os.getuid(), os.getgid()))

    def chown(self, path: Path, user: str, group: str) -> None:
        self.owners[path] = (self.uid(user), self.gid(group))

    def restore_owner(self, path: Path, uid: int, gid: int) -> None:
        self.owners[path] = (uid, gid)


class FakeSystem:
    simulated = True

    def __init__(
        self,
        controller: str = "traincapsule-controller",
        *,
        enabled: set[str] | None = None,
        active: set[str] | None = None,
        ready: bool = True,
    ) -> None:
        self.controller = controller
        self.enabled = set(enabled or ())
        self.active = set(active or ())
        self.ready = ready
        self.reloads = 0
        self.calls: list[tuple[str, str]] = []
        self.pids = {"traincapsule-controller.service": 101}
        self.fail_start_unit: str | None = None

    def system_ready(self) -> bool:
        return self.ready

    def unit_enabled(self, unit: str) -> bool:
        return unit in self.enabled

    def unit_active(self, unit: str) -> bool:
        return unit in self.active

    def unit_main_pid(self, unit: str) -> int:
        return self.pids.get(unit, 0) if unit in self.active else 0

    def daemon_reload(self) -> None:
        self.reloads += 1

    def enable_unit(self, unit: str) -> None:
        self.calls.append(("enable", unit))
        self.enabled.add(unit)

    def disable_unit(self, unit: str) -> None:
        self.calls.append(("disable", unit))
        self.enabled.discard(unit)

    def start_unit(self, unit: str) -> None:
        self.calls.append(("start", unit))
        if self.fail_start_unit == unit:
            raise RuntimeError("simulated unit start failure")
        self.active.add(unit)
        if unit == "traincapsule-controller.service":
            self.pids[unit] = self.pids.get(unit, 100) + 1

    def stop_unit(self, unit: str) -> None:
        self.calls.append(("stop", unit))
        self.active.discard(unit)

    def restart_unit(self, unit: str) -> None:
        self.calls.append(("restart", unit))
        if self.fail_start_unit == unit:
            raise RuntimeError("simulated unit restart failure")
        self.active.add(unit)
        if unit == "traincapsule-controller.service":
            self.pids[unit] = self.pids.get(unit, 100) + 1


def _directory_rows() -> list[dict[str, str]]:
    def row(target: str, owner: str, mode: str) -> dict[str, str]:
        return {"target": target, "owner": owner, "group": owner, "mode": mode}

    return [
        row("/usr/local/libexec", "root", "0755"),
        row("/var/lib/traincapsule-verifier", "root", "0755"),
        row("/etc/traincapsule-verifier", "root", "0755"),
        row("/etc/traincapsule-verifier/keys", "root", "0755"),
        row("/etc/traincapsule-verifier/request-profiles", "root", "0755"),
        row("/etc/traincapsule-canary-runner", "root", "0755"),
        row("/etc/traincapsule-runtime", "root", "0755"),
        row("/etc/traincapsule-controller", "root", "0755"),
        row("/etc/traincapsule-deployment", "root", "0755"),
        row(
            "/var/lib/traincapsule-github-token",
            "traincapsule-github-token",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-github-token/outbox",
            "traincapsule-github-token",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-verifier/anchor-fetcher-inbox",
            "traincapsule-anchor-fetcher",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-verifier/anchor-fetcher-outbox",
            "traincapsule-anchor-fetcher",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-verifier/anchor-fetcher-private",
            "traincapsule-anchor-fetcher",
            "0700",
        ),
        row("/opt/traincapsule-runtime", "root", "0755"),
        row("/opt/traincapsule-runtime/artifacts", "root", "0755"),
        row("/opt/traincapsule-runtime/wheels", "root", "0755"),
        row("/opt/traincapsule-runtime/generations", "root", "0555"),
        row("/opt/traincapsule-canary-runner", "root", "0755"),
        row("/opt/traincapsule-canary-runner/lib", "root", "0755"),
        row("/opt/traincapsule-canary-runner/lib/python3.12", "root", "0755"),
        row(
            "/opt/traincapsule-canary-runner/lib/python3.12/site-packages",
            "root",
            "0755",
        ),
        row(
            "/opt/traincapsule-canary-runner/lib/python3.12/site-packages/"
            "traincapsule_canary_runner",
            "root",
            "0755",
        ),
        row(
            "/var/lib/traincapsule-canary-secrets",
            "traincapsule-controller",
            "0700",
        ),
        row("/var/lib/traincapsule-runtime", "traincapsule-controller", "0700"),
        row("/var/lib/traincapsule-runtime/git", "traincapsule-controller", "0700"),
        row("/var/lib/traincapsule-runtime/worktrees", "traincapsule-controller", "0700"),
        row("/var/lib/traincapsule-runtime/artifacts", "traincapsule-controller", "0700"),
        row("/var/lib/traincapsule-runtime/artifacts/v3", "traincapsule-controller", "0700"),
        row(
            "/var/lib/traincapsule-runtime/deployment-update-handoffs",
            "traincapsule-controller",
            "0700",
        ),
        row("/var/lib/traincapsule-verifier/anchor-update-journal", "root", "0700"),
        row("/var/lib/traincapsule-verifier/deployment-refresh-journal", "root", "0700"),
        row("/var/lib/traincapsule-verifier/deployment-refresh-claims", "root", "0700"),
        {
            "target": "/var/lib/traincapsule-verifier/activation-refresh-inbox",
            "owner": "root",
            "group": "traincapsule-controller",
            "mode": "0750",
        },
        row(
            "/var/lib/traincapsule-verifier/activation-refresh-retirement",
            "root",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-controller",
            "traincapsule-controller",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-controller/.config",
            "traincapsule-controller",
            "0700",
        ),
        row("/etc/traincapsule-factory", "root", "0755"),
        row("/etc/traincapsule-factory/external-evidence", "root", "0755"),
        row(
            "/var/lib/traincapsule-controller/.config/traincapsule",
            "traincapsule-controller",
            "0700",
        ),
        row("/var/lib/traincapsule-external-evidence", "root", "0755"),
        row(
            "/var/lib/traincapsule-external-evidence/staged-authority",
            "root",
            "0700",
        ),
        row("/var/lib/traincapsule-external-evidence-authority", "root", "0755"),
        row("/var/lib/traincapsule-verifier/repository-boundary", "root", "0555"),
        row("/var/lib/traincapsule-verifier/anchor-updates", "root", "0700"),
        row("/var/lib/traincapsule-verifier/state", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/private", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/github-app", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/selector-private", "traincapsule-selector", "0700"),
        row("/var/lib/traincapsule-verifier/selector-outbox", "traincapsule-selector", "0700"),
        row("/var/lib/traincapsule-verifier/activation-requests", "traincapsule-selector", "0700"),
        row(
            "/var/lib/traincapsule-verifier/ruleset-private",
            "traincapsule-ruleset-observer",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-verifier/ruleset-outbox",
            "traincapsule-ruleset-observer",
            "0700",
        ),
        row("/var/lib/traincapsule-verifier/ruleset", "root", "0755"),
        row("/var/lib/traincapsule-verifier/oracle", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/outbox", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/inbox", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/activation-inbox", "traincapsule-verifier", "0700"),
        row("/var/lib/traincapsule-verifier/check-journal", "traincapsule-verifier", "0700"),
        row(
            "/var/lib/traincapsule-verifier/controller-outbox",
            "traincapsule-controller",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-verifier/activation-controller-outbox",
            "traincapsule-controller",
            "0700",
        ),
        row(
            "/var/lib/traincapsule-verifier/controller-start-outbox",
            "traincapsule-controller",
            "0700",
        ),
        row("/var/lib/traincapsule-verifier/controller-start-journal", "root", "0700"),
        row(
            "/var/lib/traincapsule-verifier/post-activation-observations",
            "root",
            "0700",
        ),
        row("/var/lib/traincapsule-verifier/activation", "root", "0755"),
        row("/var/lib/traincapsule-verifier/request-journal", "root", "0700"),
        row("/var/lib/traincapsule-verifier/receipts", "root", "0755"),
        row("/var/lib/traincapsule-verifier/journal", "root", "0700"),
    ]


def _metadata(role: str) -> tuple[str, str, str]:
    if role == "public-verifier":
        return "root", "root", "0755"
    if role == "reduction-oracle":
        return "root", "root", "0555"
    if role == "reduction-oracle-public-key":
        return "root", "root", "0444"
    if role in {"issuer", "activation-issuer", "check-worker"}:
        return "root", "traincapsule-verifier", "0750"
    if role == "observed-main-selector":
        return "root", "traincapsule-selector", "0750"
    if role == "ruleset-observer":
        return "root", "traincapsule-ruleset-observer", "0750"
    if role in {
        "receipt-broker",
        "request-broker",
        "activation-selector-broker",
        "activation-request-broker",
        "ruleset-broker",
        "controller-start-broker",
        "post-activation-observer",
        "git-anchor-updater",
        "deployment-refresh",
    }:
        return "root", "root", "0700"
    if role in {"private-key", "github-app-private-key"}:
        return "traincapsule-verifier", "traincapsule-verifier", "0600"
    if role in {"selector-private-key", "selector-credential"}:
        return "traincapsule-selector", "traincapsule-selector", "0600"
    if role in {"ruleset-private-key", "ruleset-credential"}:
        return "traincapsule-ruleset-observer", "traincapsule-ruleset-observer", "0600"
    if role == "activation-supervisor-launcher":
        return "root", "traincapsule-controller", "0750"
    if role == "github-token-refresher":
        return "root", "traincapsule-github-token", "0750"
    if role == "github-token-refresher-private-key":
        return "traincapsule-github-token", "traincapsule-github-token", "0600"
    if role == "github-token-refresher-policy":
        return "root", "root", "0444"
    if role == "deployment-refresh-policy":
        return "root", "root", "0444"
    if role in {"git-anchor-producer", "git-anchor-askpass"}:
        return "root", "traincapsule-anchor-fetcher", "0750"
    if role in {"git-anchor-github-private-key", "git-anchor-observer-private-key"}:
        return "traincapsule-anchor-fetcher", "traincapsule-anchor-fetcher", "0600"
    if role in {"git-anchor-producer-policy", "git-anchor-observer-public-key"}:
        return "root", "root", "0444"
    if role in {
        "canary-policy",
        "canary-live-probes-policy",
        "python-runtime-manifest",
        "python-runtime-archive",
        "python-runtime-distribution-manifest",
    }:
        return "root", "root", "0444"
    if role.startswith("canary-distribution-"):
        return "root", "root", "0444"
    if role == "canary-claude-token":
        return "traincapsule-controller", "traincapsule-controller", "0400"
    if role == "python-runtime":
        return "root", "root", "0555"
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
    if role == "canary-runner" or role.startswith("canary-"):
        return "root", "root", "0555"
    if role == "controller-oauth-token":
        return "traincapsule-controller", "traincapsule-controller", "0600"
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


def _build_snapshot_fixture(payload_root: Path) -> tuple[str, str]:
    snapshot = payload_root.parent / "snapshot-source"
    (snapshot / "config").mkdir(parents=True)
    source_raw = canonical_json_bytes({"generationId": "test-final-generation"})
    (snapshot / "config/source-generation.json").write_bytes(source_raw)
    (snapshot / "controller.py").write_text("# exact installed controller source\n")
    for source_prefix, _target_prefix in PROJECT_SOURCE_MAPPINGS:
        initializer = snapshot / source_prefix / "__init__.py"
        initializer.parent.mkdir(parents=True, exist_ok=True)
        initializer.write_text("# fixture dependency\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=snapshot, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=snapshot, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Snapshot Fixture",
            "-c",
            "user.email=snapshot@example.invalid",
            "commit",
            "-m",
            "exact final snapshot",
        ],
        cwd=snapshot,
        check=True,
        capture_output=True,
    )
    shutil.rmtree(snapshot / ".git/hooks")
    (snapshot / ".git/info/exclude").write_text("/SNAPSHOT_MANIFEST.json\n")
    main_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=snapshot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree_sha = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=snapshot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    for path in sorted(snapshot.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)

    entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    archive_path = payload_root / "repository-snapshot"
    archive_path.chmod(0o600)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(snapshot.rglob("*")):
            relative = path.relative_to(snapshot).as_posix()
            directory = path.is_dir()
            raw = b"" if directory else path.read_bytes()
            mode = 0o555 if directory else 0o444
            info = zipfile.ZipInfo(relative + ("/" if directory else ""))
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.create_system = 3
            info.external_attr = ((stat.S_IFDIR if directory else stat.S_IFREG) | mode) << 16
            archive.writestr(info, raw)
            entries.append(
                {
                    "path": relative,
                    "kind": "directory" if directory else "file",
                    "mode": f"0{mode:03o}",
                    "digest": None if directory else sha256_digest(raw),
                }
            )
            parts = Path(relative).parts
            if (
                not directory
                and len(parts) == 4
                and parts[:2] == (".git", "objects")
                and len(parts[2]) == 2
                and len(parts[3]) == 38
            ):
                unpacked = zlib.decompress(raw)
                header, content = unpacked.split(b"\0", 1)
                kind, _ = header.decode().split(" ", 1)
                objects.append(
                    {"objectId": parts[2] + parts[3], "kind": kind, "size": len(content)}
                )
    archive_path.chmod(0o444)
    manifest: dict[str, object] = {
        "schemaVersion": "3.1",
        "manifestDigest": "sha256:" + "0" * 64,
        "mainSha": main_sha,
        "treeSha": tree_sha,
        "sourceManifestPath": "config/source-generation.json",
        "sourceGenerationDigest": sha256_digest(source_raw),
        "effectiveConfigDigest": sha256_digest(
            (payload_root / "controller-effective-config").read_bytes()
        ),
        "pythonRuntimeManifestDigest": sha256_digest(
            (payload_root / "python-runtime-manifest").read_bytes()
        ),
        "packageManifestDigest": sha256_digest(
            (payload_root / "controller-package-manifest").read_bytes()
        ),
        "dependencyLockDigest": sha256_digest(
            (payload_root / "controller-dependency-lock").read_bytes()
        ),
        "entries": entries,
        "gitObjects": sorted(objects, key=lambda item: str(item["objectId"])),
    }
    manifest["manifestDigest"] = sha256_digest(canonical_json_bytes(manifest))
    manifest_path = payload_root / "repository-snapshot-manifest"
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    manifest_path.chmod(0o444)
    return main_sha, tree_sha


def _fixture(tmp_path: Path) -> tuple[Path, Path, PrivilegedInstallSpec, FakeAuthority, FakeSystem]:
    root = tmp_path / "root"
    for relative in ("var/lib", "etc/systemd/system", "usr/local/bin", "usr/libexec", "opt"):
        (root / relative).mkdir(parents=True, mode=0o755)
    bundle = tmp_path / "bundle"
    payload_root = bundle / "payload"
    payload_root.mkdir(parents=True)
    rendered = tmp_path / "rendered"
    rendered_paths = render_systemd_units(rendered)
    rendered_by_name = {path.name: path.read_bytes() for path in rendered_paths}
    unit_names = {
        "issuer-service": "traincapsule-verifier-issuer.service",
        "issuer-path": "traincapsule-verifier-issuer.path",
        "activation-service": "traincapsule-verifier-activation-issuer.service",
        "activation-path": "traincapsule-verifier-activation-issuer.path",
        "check-worker-service": "traincapsule-verifier-check-worker.service",
        "check-worker-path": "traincapsule-verifier-check-worker.path",
        "selector-service": "traincapsule-verifier-observed-main-selector.service",
        "selector-path": "traincapsule-verifier-observed-main-selector.path",
        "selector-broker-service": "traincapsule-verifier-activation-selector-broker.service",
        "selector-broker-path": "traincapsule-verifier-activation-selector-broker.path",
        "activation-request-service": "traincapsule-verifier-activation-request-broker.service",
        "activation-request-path": "traincapsule-verifier-activation-request-broker.path",
        "controller-start-service": "traincapsule-verifier-controller-start.service",
        "controller-start-path": "traincapsule-verifier-controller-start.path",
        "post-activation-observer-service": (
            "traincapsule-verifier-post-activation-observer.service"
        ),
        "post-activation-observer-timer": (
            "traincapsule-verifier-post-activation-observer.timer"
        ),
        "ruleset-observer-service": "traincapsule-verifier-ruleset-observer.service",
        "ruleset-observer-timer": "traincapsule-verifier-ruleset-observer.timer",
        "ruleset-broker-service": "traincapsule-verifier-ruleset-broker.service",
        "ruleset-broker-path": "traincapsule-verifier-ruleset-broker.path",
        "activation-supervisor-service": "traincapsule-activation-supervisor.service",
        "activation-supervisor-timer": "traincapsule-activation-supervisor.timer",
        "github-token-refresher-service": "traincapsule-github-token-refresher.service",
        "github-token-refresher-timer": "traincapsule-github-token-refresher.timer",
        "github-token-promoter-service": "traincapsule-github-token-promoter.service",
        "github-token-promoter-path": "traincapsule-github-token-promoter.path",
        "receipt-service": "traincapsule-verifier-broker.service",
        "receipt-path": "traincapsule-verifier-broker.path",
        "request-service": "traincapsule-verifier-request-broker.service",
        "request-path": "traincapsule-verifier-request-broker.path",
    }
    files: list[dict[str, str]] = []
    anchor_observer_key = Ed25519PrivateKey.generate()
    anchor_github_key = generate_private_key(public_exponent=65537, key_size=2048)
    publisher_github_key = generate_private_key(public_exponent=65537, key_size=2048)
    selector_signing_key = Ed25519PrivateKey.generate()
    ruleset_signing_key = Ed25519PrivateKey.generate()
    for role, target in ROLE_TARGETS.items():
        if role in unit_names and unit_names[role] in rendered_by_name:
            data = rendered_by_name[unit_names[role]]
        elif Path(target).name in rendered_by_name:
            data = rendered_by_name[Path(target).name]
        elif role == "controller-principal-policy":
            data = canonical_json_bytes(
                {"schemaVersion": "3.1", "principal": "traincapsule-controller"}
            )
        elif role == "controller-start-policy":
            data = controller_start_policy_content()
        elif role == "post-activation-policy":
            data = post_activation_policy_content()
        elif role == "git-anchor-policy":
            data = git_anchor_policy_content()
        elif role == "git-anchor-producer-policy":
            producer_policy = json.loads(git_anchor_producer_policy_content())
            producer_policy["githubAppId"] = 123
            producer_policy["installationId"] = 456
            producer_policy["requiredCheckAppIds"]["TrainCapsule / Machine policy"] = 789
            data = canonical_json_bytes(producer_policy)
        elif role == "policy":
            data = canonical_json_bytes(
                {
                    "schemaVersion": "3.1",
                    "allowedClaims": ["ACTIVATION", "CLAIM:ENGINEERING-PASS"],
                    "allowedPublicationScopes": [
                        "factory/roadmap/work_items.yaml",
                        "factory/state",
                    ],
                    "privateGateSuiteId": "FULL-RELEASE-V31",
                    "privateGateRunnerDigest": "sha256:" + "d" * 64,
                    "riskPolicies": {
                        "TRUST_CORE": {
                            "requiredGates": ["CANDIDATE-MANIFEST"],
                            "requiredOracleIds": ["ORACLE:CONFORMANCE:001"],
                            "oracleRunnerDigests": {
                                "ORACLE:CONFORMANCE:001": "sha256:" + "e" * 64
                            },
                            "acceptedEvidenceModes": ["CONTROLLED_VALIDATED"],
                        }
                    },
                }
            )
        elif role == "machine-policy-review-profile":
            data = canonical_json_bytes(
                {
                    "schemaVersion": "3.1",
                    "riskTier": "TRUST_CORE",
                    "requestedClaims": ["CLAIM:ENGINEERING-PASS"],
                    "publicationScope": ["factory/roadmap/work_items.yaml"],
                    "nativeDisposition": "UNKNOWN",
                    "valueDisposition": "EXTERNAL_EVIDENCE_REQUIRED",
                    "engineeringCeiling": "PASSED",
                    "commercialCeiling": "NATIVE_ADVANTAGE_UNPROVEN",
                    "privateGateSuiteId": "FULL-RELEASE-V31",
                    "privateGateRunnerDigest": "sha256:" + "d" * 64,
                    "oracles": {
                        "ORACLE:CONFORMANCE:001": {
                            "runnerDigest": "sha256:" + "e" * 64,
                            "nativeDisposition": "UNKNOWN",
                            "valueDisposition": "EXTERNAL_EVIDENCE_REQUIRED",
                            "engineeringCeiling": "PASSED",
                            "commercialCeiling": "NATIVE_ADVANTAGE_UNPROVEN",
                        }
                    },
                }
            )
        elif role == "activation-policy-profile":
            data = canonical_json_bytes(
                {
                    "schemaVersion": "3.1",
                    "riskTier": "TRUST_CORE",
                    "requestedClaims": ["ACTIVATION"],
                    "publicationScope": ["factory/state"],
                    "nativeDisposition": "UNKNOWN",
                    "valueDisposition": "EXTERNAL_EVIDENCE_REQUIRED",
                    "engineeringCeiling": "PASSED",
                    "commercialCeiling": "NATIVE_ADVANTAGE_UNPROVEN",
                    "privateGateSuiteId": "FULL-RELEASE-V31",
                    "privateGateRunnerDigest": "sha256:" + "d" * 64,
                    "oracles": {
                        "ORACLE:CONFORMANCE:001": {
                            "runnerDigest": "sha256:" + "e" * 64,
                            "nativeDisposition": "UNKNOWN",
                            "valueDisposition": "EXTERNAL_EVIDENCE_REQUIRED",
                            "engineeringCeiling": "PASSED",
                            "commercialCeiling": "NATIVE_ADVANTAGE_UNPROVEN",
                        }
                    },
                }
            )
        elif role in {"activation-selector-policy", "ruleset-observer-policy"}:
            data = canonical_json_bytes(
                {
                    "schemaVersion": "3.1",
                    "repository": "TasfiqJ/TrainCapsule",
                    "requiredCheckAppIds": {
                        "TrainCapsule / Docs and schemas": 15368,
                        "TrainCapsule / Factory quality": 15368,
                        "TrainCapsule / Machine policy": 789,
                        "TrainCapsule / Packaging install": 15368,
                        "TrainCapsule / Product contract": 15368,
                        "TrainCapsule / Product unit": 15368,
                        "TrainCapsule / Security": 15368,
                        "TrainCapsule / Source freshness": 15368,
                        "TrainCapsule / Source-of-truth integrity": 15368,
                    },
                    "githubAppId": 123,
                    "installationId": 456,
                    "privateKeyEnvironment": (
                        "TRAINCAPSULE_GITHUB_APP_PRIVATE_KEY_BASE64"
                    ),
                }
            )
        elif role == "github-app-private-key":
            data = publisher_github_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        elif role in {"selector-credential", "ruleset-credential"}:
            encoded = base64.b64encode(
                publisher_github_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            data = b"TRAINCAPSULE_GITHUB_APP_PRIVATE_KEY_BASE64=" + encoded + b"\n"
        elif role == "selector-private-key":
            data = selector_signing_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        elif role == "ruleset-private-key":
            data = ruleset_signing_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        elif role == "ruleset-public-key":
            data = ruleset_signing_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        elif role == "git-anchor-github-private-key":
            data = anchor_github_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        elif role == "git-anchor-observer-private-key":
            data = anchor_observer_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        elif role == "git-anchor-observer-public-key":
            data = anchor_observer_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        elif role == "activation-supervisor-launcher":
            data = (
                Path(__file__).resolve().parents[2] / "scripts/windows_activation_entrypoint.sh"
            ).read_bytes()
        elif role in {"external-evidence-service", "external-evidence-path"} or (
            role.startswith(("github-token-", "deployment-refresh-"))
            and role.endswith(("-service", "-timer", "-path"))
        ):
            data = (Path(__file__).resolve().parents[2] / "config" / Path(target).name).read_bytes()
        elif role == "controller-oauth-token":
            data = b"sk-" + b"ant-" + b"oat01-" + b"test-controller-" + b"0" * 32
        elif role == "canary-claude-token":
            data = b"sk-" + b"ant-" + b"oat01-" + b"test-canary-" + b"0" * 32
        elif role == "github-token-refresher-policy":
            data = canonical_json_bytes(
                {
                    "schemaVersion": "3.1",
                    "githubAppId": 123,
                    "installationId": 456,
                    "repository": "test-owner/isolated-canary",
                    "audience": "https://api.github.com",
                    "permissions": {
                        "actions": "write",
                        "checks": "read",
                        "contents": "read",
                        "pull_requests": "read",
                    },
                    "privateKeyPath": ROLE_TARGETS["github-token-refresher-private-key"],
                    "outboxTokenPath": "/var/lib/traincapsule-github-token/outbox/token",
                    "outboxMetadataPath": (
                        "/var/lib/traincapsule-github-token/outbox/token-metadata.json"
                    ),
                    "targetTokenPath": CANARY_GITHUB_TOKEN_TARGET,
                    "targetMetadataPath": (
                        "/var/lib/traincapsule-canary-secrets/"
                        "github-app-installation-token.json"
                    ),
                    "refreshBeforeSeconds": 600,
                }
            )
        elif role == "github-token-refresher-private-key":
            token_key = generate_private_key(public_exponent=65537, key_size=2048)
            data = token_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        elif role == "deployment-refresh-policy":
            python_raw = (payload_root / "python-runtime").read_bytes()
            dependency_raw = (payload_root / "python-runtime-manifest").read_bytes()
            data = canonical_json_bytes(
                {
                    "schemaVersion": "3.1",
                    "proposalRoot": (
                        "/var/lib/traincapsule-runtime/deployment-update-handoffs"
                    ),
                    "handoffRoot": (
                        "/var/lib/traincapsule-verifier/deployment-refresh-claims"
                    ),
                    "evidenceRoot": "/var/lib/traincapsule-verifier/anchor-updates",
                    "anchorRoot": "/var/lib/traincapsule-runtime/git",
                    "generationRoot": "/opt/traincapsule-runtime/generations",
                    "repositoryBoundary": (
                        "/var/lib/traincapsule-verifier/repository-boundary"
                    ),
                    "journalRoot": (
                        "/var/lib/traincapsule-verifier/deployment-refresh-journal"
                    ),
                    "runtimeManifestPath": (
                        "/etc/traincapsule-controller/runtime-manifest.json"
                    ),
                    "environmentPath": (
                        "/etc/traincapsule-controller/controller-runtime.env"
                    ),
                    "effectiveConfigPath": (
                        "/etc/traincapsule-controller/effective-config.yaml"
                    ),
                    "generationManifestPath": (
                        "/etc/traincapsule-controller/deployment-generation.json"
                    ),
                    "currentPointer": "/opt/traincapsule-runtime/current",
                    "pythonRuntime": "/opt/traincapsule-runtime/python/bin/python3.12",
                    "pythonRuntimeDigest": sha256_digest(python_raw),
                    "dependencyManifestPath": "/etc/traincapsule-runtime/runtime.json",
                    "dependencyManifestDigest": sha256_digest(dependency_raw),
                    "allowedSourcePrefixes": [
                        "tcfactory/",
                        "deployment/",
                        "verifier/src/traincapsule_verifier/",
                        "canary_runner/src/traincapsule_canary_runner/",
                        "packages/traincapsule-core/src/traincapsule_core/",
                        (
                            "packages/traincapsule-ingest-pytorch/src/"
                            "traincapsule_ingest_pytorch/"
                        ),
                        "packages/traincapsule-qualify/src/traincapsule_qualify/",
                        "packages/traincapsule-cli/src/traincapsule_cli/",
                    ],
                    "requiredImports": [
                        "tcfactory",
                        "deployment",
                        "traincapsule_verifier",
                        "traincapsule_canary_runner",
                        "traincapsule_core",
                        "traincapsule_ingest_pytorch",
                        "traincapsule_qualify",
                        "traincapsule_cli",
                    ],
                    "controllerUnit": "traincapsule-controller.service",
                }
            )
        elif role.startswith("canary-distribution-"):
            data = (
                Path(__file__).resolve().parents[2]
                / "canary_runner/src/traincapsule_canary_runner"
                / Path(target).name
            ).read_bytes()
        elif role == "controller-service":
            data = (
                b"[Service]\n"
                b"User=traincapsule-controller\n"
                b"Group=traincapsule-controller\n"
                b"ExecStart=/opt/traincapsule-runtime/python/bin/python3.12 -m tcfactory.cli "
                b"v3-controller --repo /var/lib/traincapsule-verifier/repository-boundary\n"
                b"EnvironmentFile=/etc/traincapsule-controller/controller-runtime.env\n"
                b"WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary\n"
                b"NoNewPrivileges=yes\n"
            )
        elif role == "controller-runtime-environment":
            data = (
                b"TCF_RUNTIME_ROOT=/var/lib/traincapsule-runtime\n"
                b"TCF_CANARY_PUBLICATION_REMOTE="
                b"https://github.com/TasfiqJ/TrainCapsule-Canary.git\n"
                b"PYTHONSAFEPATH=1\n"
                b"PYTHONNOUSERSITE=1\n"
                b"GIT_CONFIG_COUNT=1\n"
                b"GIT_CONFIG_KEY_0=safe.directory\n"
                b"GIT_CONFIG_VALUE_0=/var/lib/traincapsule-verifier/"
                b"repository-boundary\n"
                + f"PYTHONPATH={INITIAL_CONTROLLER_PYTHONPATH}\n".encode()
            )
        elif role == "controller-effective-config":
            data = b"schemaVersion: '3.1'\n"
        elif role == "python-runtime":
            elf = bytearray(120)
            elf[:6] = b"\x7fELF\x02\x01"
            elf[32:40] = (64).to_bytes(8, "little")
            elf[54:56] = (56).to_bytes(2, "little")
            elf[56:58] = (1).to_bytes(2, "little")
            elf[64:68] = (1).to_bytes(4, "little")
            data = bytes(elf)
        else:
            data = f"opaque-pinned-test-artifact:{role}\n".encode()
        owner, group, mode = _metadata(role)
        if (
            int(mode, 8) & 0o111
            and role != "python-runtime"
            and not data.startswith((b"#!", b"\x7fELF"))
        ):
            data = b"#!/opt/traincapsule-runtime/python/bin/python3.12\n" + data
        source = payload_root / role
        source.write_bytes(data)
        source.chmod(int(mode, 8))
        files.append(
            {
                "role": role,
                "source": f"payload/{role}",
                "target": target,
                "sha256": sha256_digest(data),
                "owner": owner,
                "group": group,
                "mode": mode,
            }
        )
    canary_policy = {
        "schemaVersion": "3.1",
        "runnerExecutableDigest": sha256_digest((payload_root / "canary-runner").read_bytes()),
        "distributionDigest": "sha256:" + "0" * 64,
        "mechanisms": {
            canary_id: {
                "executable": ROLE_TARGETS[f"canary-{canary_id}"],
                "executableDigest": sha256_digest(
                    (payload_root / f"canary-{canary_id}").read_bytes()
                ),
                "timeoutSeconds": 300,
                "networkAllowed": canary_id
                in {
                    "real_claude_mechanical_task",
                    "post_merge_invariant_failure_and_automated_revert_pr",
                },
            }
            for canary_id in CANARY_IDS
        },
    }
    distribution = hashlib.sha256()
    for name in sorted(
        (
            "__init__.py",
            "cli.py",
            "models.py",
            "runner.py",
            "mechanisms.py",
            "external_probes.py",
        )
    ):
        relative = name.encode()
        raw_distribution = (
            payload_root / f"canary-distribution-{name[:-3].replace('_', '-')}"
        ).read_bytes()
        distribution.update(len(relative).to_bytes(4, "big"))
        distribution.update(relative)
        distribution.update(len(raw_distribution).to_bytes(8, "big"))
        distribution.update(raw_distribution)
    canary_policy["distributionDigest"] = "sha256:" + distribution.hexdigest()
    canary_policy_raw = json.dumps(canary_policy, separators=(",", ":"), sort_keys=True).encode()
    canary_policy_path = payload_root / "canary-policy"
    canary_policy_path.chmod(0o600)
    canary_policy_path.write_bytes(canary_policy_raw)
    canary_policy_path.chmod(0o444)
    policy_pin = next(item for item in files if item["role"] == "canary-policy")
    policy_pin["sha256"] = sha256_digest(canary_policy_raw)
    live_policy = {
        "schemaVersion": "3.1",
        "claude": {
            "executable": ROLE_TARGETS["canary-claude-executable"],
            "executableDigest": sha256_digest(
                (payload_root / "canary-claude-executable").read_bytes()
            ),
            "tokenFile": ROLE_TARGETS["canary-claude-token"],
        },
        "github": {
            "executable": ROLE_TARGETS["canary-github-executable"],
            "executableDigest": sha256_digest(
                (payload_root / "canary-github-executable").read_bytes()
            ),
            "tokenFile": CANARY_GITHUB_TOKEN_TARGET,
            "repository": "test-owner/isolated-canary",
            "workflow": "traincapsule-post-merge-revert-canary.yml",
        },
    }
    live_policy_raw = json.dumps(live_policy, separators=(",", ":"), sort_keys=True).encode()
    live_policy_path = payload_root / "canary-live-probes-policy"
    live_policy_path.chmod(0o600)
    live_policy_path.write_bytes(live_policy_raw)
    live_policy_path.chmod(0o444)
    live_policy_pin = next(item for item in files if item["role"] == "canary-live-probes-policy")
    live_policy_pin["sha256"] = sha256_digest(live_policy_raw)
    runtime_source = payload_root.parent / "python-distribution-source"
    (runtime_source / "bin").mkdir(parents=True)
    (runtime_source / "lib/python3.12").mkdir(parents=True)
    runtime_executable = runtime_source / "bin/python3.12"
    runtime_executable.write_bytes((payload_root / "python-runtime").read_bytes())
    runtime_executable.chmod(0o555)
    (runtime_source / "lib/python3.12/os.py").write_text("# fixture stdlib\n")
    dependency_source = payload_root.parent / "dependency-site-packages"
    for import_name in COMPLETE_RUNTIME_IMPORTS:
        package = dependency_source / import_name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("# fixture dependency\n")
    built_archive, built_manifest = build_runtime_distribution(
        payload_root.parent / "python-runtime.zip",
        python_root=runtime_source,
        dependency_root=dependency_source,
        python_version="3.12.13",
        required_imports=COMPLETE_RUNTIME_IMPORTS,
    )
    for role, source in (
        ("python-runtime-archive", built_archive),
        ("python-runtime-distribution-manifest", built_manifest),
    ):
        target = payload_root / role
        target.chmod(0o600)
        target.write_bytes(source.read_bytes())
        target.chmod(0o444)
        pin = next(item for item in files if item["role"] == role)
        pin["sha256"] = sha256_digest(target.read_bytes())

    runtime_manifest = {
        "schemaVersion": "3.1",
        "pythonVersion": "3.12.13",
        "executableDigest": sha256_digest((payload_root / "python-runtime").read_bytes()),
        "selfContainedDistribution": True,
        "distributionDigest": sha256_digest(
            (payload_root / "python-runtime-archive").read_bytes()
        ),
        "distributionManifestDigest": sha256_digest(
            (payload_root / "python-runtime-distribution-manifest").read_bytes()
        ),
        "dependencyLockDigest": sha256_digest(
            (payload_root / "controller-dependency-lock").read_bytes()
        ),
        "requiredImports": list(COMPLETE_RUNTIME_IMPORTS),
        "dependencies": [
            {
                "name": name,
                "version": "1.0",
                "wheelDigest": sha256_digest((payload_root / role).read_bytes()),
            }
            for name, role in (
                ("pydantic", "runtime-pydantic-wheel"),
                ("pydantic-core", "runtime-pydantic-core-wheel"),
                ("typing-extensions", "runtime-typing-extensions-wheel"),
                ("typing-inspection", "runtime-typing-inspection-wheel"),
                ("cryptography", "runtime-cryptography-wheel"),
                ("cffi", "runtime-cffi-wheel"),
                ("pycparser", "runtime-pycparser-wheel"),
            )
        ],
        "applications": [
            {
                "name": name,
                "wheelDigest": sha256_digest((payload_root / role).read_bytes()),
            }
            for name, role in (
                ("verifier", "runtime-verifier-wheel"),
                ("controller", "runtime-controller-wheel"),
                ("deployment", "runtime-deployment-wheel"),
                ("canary-runner", "runtime-canary-wheel"),
            )
        ],
    }
    runtime_manifest_raw = json.dumps(
        runtime_manifest, separators=(",", ":"), sort_keys=True
    ).encode()
    runtime_manifest_path = payload_root / "python-runtime-manifest"
    runtime_manifest_path.chmod(0o600)
    runtime_manifest_path.write_bytes(runtime_manifest_raw)
    runtime_manifest_path.chmod(0o444)
    runtime_manifest_pin = next(item for item in files if item["role"] == "python-runtime-manifest")
    runtime_manifest_pin["sha256"] = sha256_digest(runtime_manifest_raw)
    refresh_policy_path = payload_root / "deployment-refresh-policy"
    refresh_policy = cast(dict[str, object], json.loads(refresh_policy_path.read_bytes()))
    refresh_policy["dependencyManifestDigest"] = sha256_digest(runtime_manifest_raw)
    refresh_policy_path.chmod(0o600)
    refresh_policy_path.write_bytes(canonical_json_bytes(refresh_policy))
    refresh_policy_path.chmod(0o444)
    refresh_policy_pin = next(
        item for item in files if item["role"] == "deployment-refresh-policy"
    )
    refresh_policy_pin["sha256"] = sha256_digest(refresh_policy_path.read_bytes())
    repository_main_sha, repository_tree_sha = _build_snapshot_fixture(payload_root)
    for role in ("repository-snapshot", "repository-snapshot-manifest"):
        pin = next(item for item in files if item["role"] == role)
        pin["sha256"] = sha256_digest((payload_root / role).read_bytes())
    snapshot_payload = json.loads((payload_root / "repository-snapshot-manifest").read_bytes())
    for role in ("git-anchor-policy", "git-anchor-producer-policy"):
        policy_path = payload_root / role
        policy = cast(dict[str, object], json.loads(policy_path.read_bytes()))
        policy["sourceGenerationDigest"] = snapshot_payload["sourceGenerationDigest"]
        policy_path.chmod(0o600)
        policy_path.write_bytes(canonical_json_bytes(policy))
        policy_path.chmod(int(_metadata(role)[2], 8))
        pin = next(item for item in files if item["role"] == role)
        pin["sha256"] = sha256_digest(policy_path.read_bytes())
    controller_artifact_roles = {
        "pythonRuntime": ("python-runtime", True),
        "packageManifest": ("controller-package-manifest", False),
        "dependencyLock": ("controller-dependency-lock", False),
        "controllerUnit": ("controller-service", False),
        "environmentFile": ("controller-runtime-environment", False),
        "effectiveConfig": ("controller-effective-config", False),
        "repositorySnapshotManifest": ("repository-snapshot-manifest", False),
    }
    controller_runtime_manifest: dict[str, object] = {
        "schemaVersion": "3.1",
        "manifestDigest": "sha256:" + "0" * 64,
        "controllerPrincipal": "traincapsule-controller",
        "serviceName": "traincapsule-controller.service",
        "distributionRoot": "/opt/traincapsule-runtime",
        "repositoryRoot": "/var/lib/traincapsule-verifier/repository-boundary",
        "runtimeRoot": "/var/lib/traincapsule-runtime",
        "repositoryMainSha": repository_main_sha,
        "repositoryTreeSha": repository_tree_sha,
        "mutableGitRoot": "/var/lib/traincapsule-runtime/git",
        "mutableWorktreeRoot": "/var/lib/traincapsule-runtime/worktrees",
        "artifactRoot": "/var/lib/traincapsule-runtime/artifacts/v3",
        "entryArguments": [
            "-m",
            "tcfactory.cli",
            "v3-controller",
            "--repo",
            "/var/lib/traincapsule-verifier/repository-boundary",
        ],
        "reductionOracle": {
            "oracleId": "TRAINCAPSULE_REDUCTION_ORACLE_V1",
            "executable": {
                "path": ROLE_TARGETS["reduction-oracle"],
                "digest": sha256_digest(
                    (payload_root / "reduction-oracle").read_bytes()
                ),
                "executable": True,
            },
            "publicKey": {
                "path": ROLE_TARGETS["reduction-oracle-public-key"],
                "digest": sha256_digest(
                    (payload_root / "reduction-oracle-public-key").read_bytes()
                ),
                "executable": False,
            },
            "receiptVerifier": {
                "path": ROLE_TARGETS["public-verifier"],
                "digest": sha256_digest(
                    (payload_root / "public-verifier").read_bytes()
                ),
                "executable": True,
            },
            "publicReceiptRoot": "/var/lib/traincapsule-verifier/receipts",
            "activationReceiptPath": (
                "/var/lib/traincapsule-verifier/activation/current.json"
            ),
        },
    }
    for field, (role, executable) in controller_artifact_roles.items():
        controller_runtime_manifest[field] = {
            "path": ROLE_TARGETS[role],
            "digest": sha256_digest((payload_root / role).read_bytes()),
            "executable": executable,
        }
    controller_runtime_manifest["manifestDigest"] = sha256_digest(
        canonical_json_bytes(controller_runtime_manifest)
    )
    controller_runtime_raw = canonical_json_bytes(controller_runtime_manifest)
    controller_runtime_path = payload_root / "installed-controller-runtime-manifest"
    controller_runtime_path.chmod(0o600)
    controller_runtime_path.write_bytes(controller_runtime_raw)
    controller_runtime_path.chmod(0o444)
    controller_runtime_pin = next(
        item for item in files if item["role"] == "installed-controller-runtime-manifest"
    )
    controller_runtime_pin["sha256"] = sha256_digest(controller_runtime_raw)
    authority_key = Ed25519PrivateKey.generate()
    authority_public = authority_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    revocations_raw = canonical_json_bytes(
        {
            "authorityId": "TEST-AUTHORITY",
            "epoch": 1,
            "expiresAt": "2099-01-01T00:00:00Z",
            "issuedAt": "2026-08-12T00:00:00Z",
            "issuerId": "test-issuer",
            "keyId": "test-key",
            "previousListDigest": None,
            "revocationVersion": 1,
            "revokedNonces": [],
            "revokedReceiptIds": [],
        }
    )
    anchor_raw = canonical_json_bytes(
        {
            "anchorVersion": 1,
            "authorityId": "TEST-AUTHORITY",
            "currentRevocationDigest": sha256_digest(revocations_raw),
            "epoch": 1,
            "expiresAt": "2099-01-01T00:00:00Z",
            "issuedAt": "2026-08-12T00:00:00Z",
            "issuerId": "test-issuer",
            "keyId": "test-key",
            "previousRevocationDigest": None,
        }
    )
    authority_values = {
        "external-evidence-public-key": authority_public,
        "external-evidence-revocations": revocations_raw,
        "external-evidence-revocations-signature": authority_key.sign(revocations_raw),
        "external-evidence-authority-anchor": anchor_raw,
        "external-evidence-authority-anchor-signature": authority_key.sign(anchor_raw),
    }
    for role, raw_bytes in authority_values.items():
        authority_path = payload_root / role
        authority_path.chmod(0o600)
        authority_path.write_bytes(raw_bytes)
        authority_path.chmod(int(_metadata(role)[2], 8))
        pin = next(item for item in files if item["role"] == role)
        pin["sha256"] = sha256_digest(raw_bytes)
    oracle_data = b"#!/bin/sh\nexit 1\n"
    oracle_source = payload_root / "oracle-test-runner"
    oracle_source.write_bytes(oracle_data)
    oracle_source.chmod(0o500)
    files.append(
        {
            "role": "oracle-0123456789abcdef",
            "source": "payload/oracle-test-runner",
            "target": "/var/lib/traincapsule-verifier/oracle/test-runner",
            "sha256": sha256_digest(oracle_data),
            "owner": "traincapsule-verifier",
            "group": "traincapsule-verifier",
            "mode": "0500",
        }
    )
    raw: dict[str, object] = {
        "schemaVersion": "3.1",
        "state": "STAGED_NOT_INSTALLED",
        "manifestDigest": "sha256:" + "0" * 64,
        "serviceAccount": {
            "name": "traincapsule-verifier",
            "home": "/var/lib/traincapsule-verifier",
            "shell": "/usr/sbin/nologin",
        },
        "selectorAccount": {
            "name": "traincapsule-selector",
            "home": "/var/lib/traincapsule-verifier/selector-private",
            "shell": "/usr/sbin/nologin",
        },
        "rulesetAccount": {
            "name": "traincapsule-ruleset-observer",
            "home": "/var/lib/traincapsule-verifier/ruleset-private",
            "shell": "/usr/sbin/nologin",
        },
        "tokenRefresherAccount": {
            "name": "traincapsule-github-token",
            "home": "/var/lib/traincapsule-github-token",
            "shell": "/usr/sbin/nologin",
        },
        "anchorFetcherAccount": {
            "name": "traincapsule-anchor-fetcher",
            "home": "/var/lib/traincapsule-verifier/anchor-fetcher-private",
            "shell": "/usr/sbin/nologin",
        },
        "controllerAccount": {
            "name": "traincapsule-controller",
            "home": "/var/lib/traincapsule-controller",
            "shell": "/usr/sbin/nologin",
        },
        "directories": _directory_rows(),
        "files": files,
        "controllerUnit": "traincapsule-controller.service",
        "pathUnits": list(PATH_UNITS),
        "generatesCredentials": False,
        "generatesReceipts": False,
        "runsOracles": False,
    }
    raw["manifestDigest"] = unsigned_manifest_digest(raw)
    spec = PrivilegedInstallSpec.model_validate(raw)
    authority = FakeAuthority()
    system = FakeSystem()
    return root, bundle, spec, authority, system


def _installer(
    root: Path,
    bundle: Path,
    spec: PrivilegedInstallSpec,
    authority: FakeAuthority,
    system: FakeSystem,
    *,
    fail_hook: object = None,
) -> PrivilegedInstaller:
    return PrivilegedInstaller(
        bundle,
        spec,
        root=root,
        authority=authority,
        system=system,
        fail_hook=fail_hook,  # type: ignore[arg-type]
    )


def test_default_is_read_only_and_apply_attests_exact_tree(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    installer = _installer(root, bundle, spec, authority, system)
    before = {path.relative_to(root) for path in root.rglob("*")}
    preview = installer.apply()
    assert isinstance(preview, InstallPreview)
    assert not preview.mutates_system
    assert {path.relative_to(root) for path in root.rglob("*")} == before

    result = installer.apply(APPLY_CONFIRMATION)
    assert isinstance(result, DeploymentAttestation)
    assert result.state == "PATH_UNITS_ENABLED"
    assert result.controller_principal == "traincapsule-controller"
    assert not result.authority_receipt_issued
    assert not result.activation_receipt_issued
    assert not result.oracle_outcome_claimed
    assert not result.controller_runtime_bound
    assert result.controller_service_stopped
    assert system.enabled == {*PATH_UNITS}
    assert "traincapsule-controller.service" not in system.active
    assert "traincapsule-verifier-post-activation-observer.timer" in system.enabled
    assert "traincapsule-verifier-git-anchor-updater.path" in system.enabled
    authority_bootstrap = (
        "start",
        "traincapsule-external-evidence-authority.service",
    )
    authority_path_start = (
        "start",
        "traincapsule-external-evidence-authority.path",
    )
    assert authority_bootstrap in system.calls
    assert system.calls.index(authority_bootstrap) < system.calls.index(authority_path_start)
    assert (
        "stop",
        "traincapsule-external-evidence-authority.service",
    ) in system.calls
    assert not any(
        action == "start" and unit == "traincapsule-controller.service"
        for action, unit in system.calls
    )
    updater = root / "usr/libexec/traincapsule-verifier-git-anchor-updater"
    updater_pin = next(item for item in spec.files if item.role == "git-anchor-updater")
    assert sha256_digest(updater.read_bytes()) == updater_pin.sha256
    assert stat.S_IMODE(updater.stat().st_mode) == 0o700
    assert authority.owner(updater) == (0, 0)
    assert PATH_UNITS.index("traincapsule-verifier-controller-start.path") < PATH_UNITS.index(
        "traincapsule-activation-supervisor.timer"
    )
    assert system.reloads == 1
    assert installer.apply(APPLY_CONFIRMATION) == result
    snapshot_index = root / "var/lib/traincapsule-verifier/repository-boundary/.git/index"
    assert stat.S_IMODE(snapshot_index.stat().st_mode) == 0o444
    stop = root / "var/lib/traincapsule-runtime/STOP"
    assert stop.read_bytes() == b"stopped pending independent activation\n"
    assert stat.S_IMODE(stop.stat().st_mode) == 0o600
    controller_uid = authority.uid("traincapsule-controller")
    assert authority.owner(stop) == (controller_uid, controller_uid)


def test_production_apply_rejects_missing_systemd_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, bundle, spec, authority, _ = _fixture(tmp_path)
    authority.simulated = False
    system = FakeSystem(ready=False)
    system.simulated = False
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    installer = PrivilegedInstaller(
        bundle,
        spec,
        root=Path("/"),
        authority=authority,
        system=system,
    )

    with pytest.raises(
        InstallFailure,
        match="production apply requires a booted and reachable systemd manager",
    ):
        installer.apply(APPLY_CONFIRMATION)

    assert not authority.accounts
    assert not system.calls
    assert installer._state == {}  # pyright: ignore[reportPrivateUsage]


def test_partial_crash_replays_from_durable_journal(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    crashed = False

    def crash_once(transition: str) -> NoReturn | None:
        nonlocal crashed
        if not crashed and transition == "file:issuer":
            crashed = True
            raise Crash("power loss")
        return None

    first = _installer(root, bundle, spec, authority, system, fail_hook=crash_once)
    with pytest.raises(Crash, match="power loss"):
        first.apply(APPLY_CONFIRMATION)
    assert not system.enabled

    replay = _installer(root, bundle, spec, authority, system)
    result = replay.apply(APPLY_CONFIRMATION)
    assert isinstance(result, DeploymentAttestation)
    assert result.state == "PATH_UNITS_ENABLED"
    events = (replay.txn / "events.jsonl").read_text(encoding="utf-8")
    assert events.count('"event":"BEGIN"') == 1
    assert '"event":"COMMIT"' in events


def test_wrong_owner_mode_and_digest_substitution_fail_closed(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    source = bundle / "payload/public-verifier"
    source.write_bytes(source.read_bytes() + b"substitution")
    installer = _installer(root, bundle, spec, authority, system)
    with pytest.raises(InstallFailure, match="source digest mismatch"):
        installer.apply(APPLY_CONFIRMATION)
    assert not (root / "var/lib/traincapsule-verifier").exists()

    root, bundle, spec, authority, system = _fixture(tmp_path / "second")
    installer = _installer(root, bundle, spec, authority, system)
    installer.apply(APPLY_CONFIRMATION)
    public = root / ROLE_TARGETS["public-verifier"].lstrip("/")
    authority.owners[public] = (999, 999)
    with pytest.raises(InstallFailure, match="owner mismatch"):
        installer.attest(require_paths=True)
    authority.chown(public, "root", "root")
    public.chmod(0o777)
    with pytest.raises(InstallFailure, match="mode mismatch"):
        installer.attest(require_paths=True)


def test_controller_cannot_gain_key_or_private_worker_access(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    installer = _installer(root, bundle, spec, authority, system)
    installer.apply(APPLY_CONFIRMATION)
    authority.memberships["traincapsule-controller"].add(authority.gid("traincapsule-verifier"))
    with pytest.raises(InstallFailure, match="negative access attestation failed"):
        installer.attest(require_paths=True)


def test_rollback_restores_preexisting_bytes_and_is_idempotent(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    public = root / ROLE_TARGETS["public-verifier"].lstrip("/")
    public.write_bytes(b"previous-version\n")
    public.chmod(0o700)
    authority.chown(public, "root", "root")
    installer = _installer(root, bundle, spec, authority, system)
    installer.apply(APPLY_CONFIRMATION)
    assert public.read_bytes() != b"previous-version\n"
    installer.rollback()
    installer.rollback()
    assert public.read_bytes() == b"previous-version\n"
    assert public.stat().st_mode & 0o777 == 0o700
    assert not system.enabled
    assert authority.accounts == {
        "traincapsule-verifier",
        "traincapsule-selector",
        "traincapsule-ruleset-observer",
            "traincapsule-github-token",
            "traincapsule-anchor-fetcher",
            "traincapsule-controller",
    }
    assert '"event":"ROLLBACK_COMPLETE"' in (installer.txn / "events.jsonl").read_text()


def test_rollback_restores_exact_preexisting_unit_states(tmp_path: Path) -> None:
    root, bundle, spec, authority, _ = _fixture(tmp_path)
    initial_enabled = {PATH_UNITS[0], PATH_UNITS[1]}
    initial_active = {PATH_UNITS[0], PATH_UNITS[2]}
    system = FakeSystem(enabled=initial_enabled, active=initial_active)
    installer = _installer(root, bundle, spec, authority, system)

    installer.apply(APPLY_CONFIRMATION)
    assert system.enabled == {*PATH_UNITS}
    assert system.active == {*PATH_UNITS}
    installer.rollback()

    assert system.enabled == initial_enabled
    assert system.active == initial_active
    events = (installer.txn / "events.jsonl").read_text(encoding="utf-8")
    assert '"event":"UNIT_BASELINES_CAPTURED"' in events


def test_direct_rollback_without_initialized_journal_has_no_effect(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    system.enabled.add(PATH_UNITS[0])
    system.active.add(PATH_UNITS[0])
    installer = _installer(root, bundle, spec, authority, system)

    installer.rollback()

    assert system.enabled == {PATH_UNITS[0]}
    assert system.active == {PATH_UNITS[0]}
    assert system.calls == []
    assert system.reloads == 0
    assert not installer.txn.exists()


def test_enable_succeeds_start_fails_and_rollback_undoes_only_enable(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    system.fail_start_unit = PATH_UNITS[0]
    installer = _installer(root, bundle, spec, authority, system)

    with pytest.raises(RuntimeError, match="start failure"):
        installer.apply(APPLY_CONFIRMATION)

    assert PATH_UNITS[0] not in system.enabled
    assert PATH_UNITS[0] not in system.active
    assert ("enable", PATH_UNITS[0]) in system.calls
    assert ("disable", PATH_UNITS[0]) in system.calls
    events = (installer.txn / "events.jsonl").read_text(encoding="utf-8")
    assert '"event":"PATH_START_FAILED"' in events


def test_apply_restarts_cleanly_after_completed_rollback(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    system.fail_start_unit = PATH_UNITS[0]
    installer = _installer(root, bundle, spec, authority, system)

    with pytest.raises(RuntimeError, match="start failure"):
        installer.apply(APPLY_CONFIRMATION)

    system.fail_start_unit = None
    result = installer.apply(APPLY_CONFIRMATION)
    assert isinstance(result, DeploymentAttestation)
    assert result.state == "PATH_UNITS_ENABLED"
    events = (installer.txn / "events.jsonl").read_text(encoding="utf-8")
    assert '"event":"BEGIN_RETRY"' in events


def test_preexisting_controller_process_blocks_install_without_mutation(tmp_path: Path) -> None:
    root, bundle, spec, authority, _ = _fixture(tmp_path)
    controller = "traincapsule-controller.service"
    system = FakeSystem(enabled={controller}, active={controller})
    installer = _installer(root, bundle, spec, authority, system)

    with pytest.raises(InstallFailure, match="active controller cannot be adopted"):
        installer.apply(APPLY_CONFIRMATION)

    assert system.enabled == {controller}
    assert system.active == {controller}
    assert system.calls == []
    assert not (root / ROLE_TARGETS["issuer"].lstrip("/")).exists()
    assert not installer.txn.exists()


def _assembly_inputs(bundle: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    payload = bundle / "payload"
    oauth_source = bundle.parent / "external/.config/traincapsule/claude-oauth-token"
    oauth_source.parent.mkdir(parents=True)
    oauth_source.write_bytes((payload / "controller-oauth-token").read_bytes())
    oauth_source.chmod(0o600)
    artifacts = {role: (payload / role).resolve() for role in ROLE_TARGETS}
    artifacts["controller-oauth-token"] = oauth_source.resolve()
    artifacts["canary-claude-token"] = oauth_source.resolve()
    return (
        artifacts,
        {"test-runner": (payload / "oracle-test-runner").resolve()},
    )


def _assembler_repo(tmp_path: Path, artifacts: dict[str, Path]) -> Path:
    source_repo = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repository"
    launcher = repo / "scripts/windows_activation_entrypoint.sh"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes((source_repo / "scripts/windows_activation_entrypoint.sh").read_bytes())
    launcher.chmod(0o555)
    artifacts["activation-supervisor-launcher"] = launcher.resolve()
    config = repo / "config"
    config.mkdir()
    for name in (
        "traincapsule-controller-runtime.env",
        "traincapsule-external-evidence-authority.service",
        "traincapsule-external-evidence-authority.path",
        "traincapsule-github-token-refresher.service",
        "traincapsule-github-token-refresher.timer",
        "traincapsule-github-token-promoter.service",
        "traincapsule-github-token-promoter.path",
        "traincapsule-deployment-refresh.service",
        "traincapsule-deployment-refresh.path",
        "traincapsule-deployment-refresh-claim.service",
        "traincapsule-deployment-refresh-claim.path",
        "traincapsule-deployment-refresh-completion.service",
        "traincapsule-deployment-refresh-completion.path",
    ):
        (config / name).write_bytes((source_repo / "config" / name).read_bytes())
    package = repo / "canary_runner/src/traincapsule_canary_runner"
    package.mkdir(parents=True)
    for source in (source_repo / "canary_runner/src/traincapsule_canary_runner").glob("*.py"):
        (package / source.name).write_bytes(source.read_bytes())
    return repo


def test_bundle_assembly_is_deterministic_and_loadable(tmp_path: Path) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path)
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)

    first = assemble_bundle(
        tmp_path / "stage-one",
        artifacts=artifacts,
        oracles=oracles,
        repo_root=repo_root,
    )
    second = assemble_bundle(
        tmp_path / "stage-two",
        artifacts=artifacts,
        oracles=oracles,
        repo_root=repo_root,
    )

    assert first == second
    assert first.state == "STAGED_NOT_INSTALLED"
    assert (tmp_path / "stage-one/installer-manifest.json").read_bytes() == (
        tmp_path / "stage-two/installer-manifest.json"
    ).read_bytes()
    assert PrivilegedInstaller.load(tmp_path / "stage-one").spec == first


def test_bundle_assembly_rejects_tamper_duplicate_and_repo_secret(tmp_path: Path) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path)
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)
    artifacts["issuer-service"].write_bytes(b"substituted unit\n")
    with pytest.raises(BundleAssemblyError, match="repository-pinned artifact mismatch"):
        assemble_bundle(
            tmp_path / "tampered",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )
    assert not (tmp_path / "tampered").exists()

    _, bundle, _, _, _ = _fixture(tmp_path / "duplicate")
    artifacts, oracles = _assembly_inputs(bundle)
    artifacts["issuer"] = artifacts["public-verifier"]
    with pytest.raises(BundleAssemblyError, match="duplicate artifact"):
        assemble_bundle(
            tmp_path / "duplicate-stage",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )

    secret = repo_root / "secrets/.unsafe-installer-secret"
    secret.parent.mkdir()
    secret.write_bytes(b"must-not-enter-repository")
    secret.chmod(0o600)
    try:
        artifacts["private-key"] = secret
        with pytest.raises(BundleAssemblyError, match="outside the repository"):
            assemble_bundle(
                tmp_path / "repo-secret",
                artifacts=artifacts,
                oracles=oracles,
                repo_root=repo_root,
            )
    finally:
        secret.unlink()


def test_bundle_cli_blocks_missing_inputs_without_leaking_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    secret_marker = "never-print-this-secret"
    missing = tmp_path / secret_marker

    result = main(
        [
            "--stage",
            str(tmp_path / "stage"),
            "--repo-root",
            str(repo_root),
            "--artifact",
            f"private-key={missing}",
        ]
    )

    output = capsys.readouterr().out
    assert result == 2
    assert '"state": "BLOCKED"' in output
    assert secret_marker not in output
    assert not (tmp_path / "stage").exists()


def test_bundle_rejects_repo_or_user_runtime_interpreter(tmp_path: Path) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path)
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)
    unsafe = bundle.parent / "unsafe-canary-runner"
    unsafe.write_bytes(b"#!/home/jasim/.local/share/uv/python/python3\n")
    unsafe.chmod(0o555)
    artifacts["canary-runner"] = unsafe.resolve()

    with pytest.raises(BundleAssemblyError, match="unsafe runtime"):
        assemble_bundle(
            tmp_path / "unsafe-runtime",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )

    assert not (tmp_path / "unsafe-runtime").exists()


def test_bundle_rejects_controller_runtime_manifest_divergence(tmp_path: Path) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path)
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)
    manifest_path = artifacts["installed-controller-runtime-manifest"]
    manifest = cast(dict[str, object], json.loads(manifest_path.read_bytes()))
    manifest["entryArguments"] = ["-m", "tcfactory.cli", "v3-controller"]
    manifest["manifestDigest"] = "sha256:" + "0" * 64
    manifest["manifestDigest"] = sha256_digest(canonical_json_bytes(manifest))
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    manifest_path.chmod(0o444)

    with pytest.raises(BundleAssemblyError, match="runtime contract is not exact"):
        assemble_bundle(
            tmp_path / "divergent-runtime",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )

    assert not (tmp_path / "divergent-runtime").exists()


def test_repository_snapshot_tamper_and_crash_replay_fail_closed(tmp_path: Path) -> None:
    root, bundle, spec, authority, system = _fixture(tmp_path)
    archive = bundle / "payload/repository-snapshot"
    archive.chmod(0o600)
    archive.write_bytes(archive.read_bytes() + b"substitution")
    archive.chmod(0o444)
    with pytest.raises(InstallFailure, match="source digest mismatch"):
        _installer(root, bundle, spec, authority, system).apply(APPLY_CONFIRMATION)

    root, bundle, spec, authority, system = _fixture(tmp_path / "replay")
    crashed = False

    def crash_once(transition: str) -> None:
        nonlocal crashed
        if not crashed and transition.endswith("config/source-generation.json"):
            crashed = True
            raise Crash("snapshot extraction interrupted")

    with pytest.raises(Crash, match="snapshot extraction interrupted"):
        _installer(
            root,
            bundle,
            spec,
            authority,
            system,
            fail_hook=crash_once,
        ).apply(APPLY_CONFIRMATION)
    result = _installer(root, bundle, spec, authority, system).apply(APPLY_CONFIRMATION)
    assert isinstance(result, DeploymentAttestation)
    assert result.state == "PATH_UNITS_ENABLED"


def test_repository_snapshot_rejects_manifest_binding_tamper(
    tmp_path: Path,
) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path)
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)
    manifest_path = artifacts["repository-snapshot-manifest"]
    manifest = cast(dict[str, object], json.loads(manifest_path.read_bytes()))
    manifest["effectiveConfigDigest"] = "sha256:" + "f" * 64
    manifest["manifestDigest"] = "sha256:" + "0" * 64
    manifest["manifestDigest"] = sha256_digest(canonical_json_bytes(manifest))
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    manifest_path.chmod(0o444)

    with pytest.raises(BundleAssemblyError, match="deployment binding is inconsistent"):
        assemble_bundle(
            tmp_path / "snapshot-binding-tamper",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )


def test_assembler_rejects_anchor_producer_key_substitution(tmp_path: Path) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path / "anchor-keys")
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)
    public_path = artifacts["git-anchor-observer-public-key"]
    public_path.chmod(0o600)
    public_path.write_bytes(
        Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    public_path.chmod(0o444)
    with pytest.raises(BundleAssemblyError, match="observer key pair does not match"):
        assemble_bundle(
            tmp_path / "anchor-key-substitution",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )


def test_assembler_rejects_anchor_producer_generation_divergence(tmp_path: Path) -> None:
    _, bundle, _, _, _ = _fixture(tmp_path / "anchor-generation")
    artifacts, oracles = _assembly_inputs(bundle)
    repo_root = _assembler_repo(tmp_path, artifacts)
    policy_path = artifacts["git-anchor-producer-policy"]
    policy = cast(dict[str, object], json.loads(policy_path.read_bytes()))
    policy["sourceGenerationDigest"] = "sha256:" + "a" * 64
    policy_path.chmod(0o600)
    policy_path.write_bytes(canonical_json_bytes(policy))
    policy_path.chmod(0o444)
    with pytest.raises(BundleAssemblyError, match="producer policy is unsafe"):
        assemble_bundle(
            tmp_path / "anchor-generation-divergence",
            artifacts=artifacts,
            oracles=oracles,
            repo_root=repo_root,
        )
