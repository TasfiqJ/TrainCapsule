"""Transactional installer for an externally assembled verifier distribution.

The module deliberately has no key-generation, receipt-issuance, oracle-execution, Git,
or network capability.  Its default operation is a read-only preflight.  Production
application requires an explicit confirmation token, uid 0, an immutable root-owned
bundle, and a stopped controller whose later start is delegated to the receipt-gated
root broker.
"""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import stat
import subprocess
import zipfile
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, cast

from pydantic import Field, model_validator
from traincapsule_verifier.bootstrap import production_install_manifest
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.models import StrictModel

from .runtime_distribution import (
    RuntimeDistributionManifest,
    extract_runtime_distribution,
    validate_extracted_runtime_distribution,
    validate_runtime_distribution,
)

APPLY_CONFIRMATION = "APPLY_PRIVILEGED_INSTALL"
SERVICE_USER = "traincapsule-verifier"
SELECTOR_USER = "traincapsule-selector"
RULESET_USER = "traincapsule-ruleset-observer"
TOKEN_REFRESHER_USER = "traincapsule-github-token"
ANCHOR_FETCHER_USER = "traincapsule-anchor-fetcher"
DEFAULT_CONTROLLER_USER = "traincapsule-controller"
INITIAL_CONTROLLER_PYTHONPATH = ":".join(
    (
        "/var/lib/traincapsule-verifier/repository-boundary",
        "/var/lib/traincapsule-verifier/repository-boundary/packages/traincapsule-core/src",
        (
            "/var/lib/traincapsule-verifier/repository-boundary/"
            "packages/traincapsule-ingest-pytorch/src"
        ),
        "/var/lib/traincapsule-verifier/repository-boundary/packages/traincapsule-qualify/src",
        "/var/lib/traincapsule-verifier/repository-boundary/packages/traincapsule-cli/src",
        "/var/lib/traincapsule-verifier/repository-boundary/verifier/src",
        "/var/lib/traincapsule-verifier/repository-boundary/canary_runner/src",
    )
)
CANARY_GITHUB_TOKEN_TARGET = (
    "/var/lib/traincapsule-canary-secrets/github-app-installation-token"
)

FileRole = Literal[
    "public-verifier",
    "issuer",
    "receipt-broker",
    "request-broker",
    "activation-issuer",
    "check-worker",
    "observed-main-selector",
    "activation-selector-broker",
    "activation-request-broker",
    "controller-start-broker",
    "post-activation-observer",
    "ruleset-observer",
    "ruleset-broker",
    "git-anchor-updater",
    "git-anchor-producer",
    "git-anchor-askpass",
    "activation-supervisor-launcher",
    "canary-runner",
    "canary-policy",
    "canary-live-probes-policy",
    "canary-receipt-probe",
    "python-runtime",
    "python-runtime-manifest",
    "python-runtime-archive",
    "python-runtime-distribution-manifest",
    "runtime-verifier-wheel",
    "runtime-controller-wheel",
    "runtime-deployment-wheel",
    "runtime-canary-wheel",
    "runtime-pydantic-wheel",
    "runtime-pydantic-core-wheel",
    "runtime-typing-extensions-wheel",
    "runtime-typing-inspection-wheel",
    "runtime-cryptography-wheel",
    "runtime-cffi-wheel",
    "runtime-pycparser-wheel",
    "canary-claude-token",
    "controller-oauth-token",
    "external-evidence-broker",
    "external-evidence-public-key",
    "external-evidence-revocations",
    "external-evidence-revocations-signature",
    "external-evidence-authority-anchor",
    "external-evidence-authority-anchor-signature",
    "external-evidence-service",
    "external-evidence-path",
    "private-key",
    "github-app-private-key",
    "selector-private-key",
    "selector-credential",
    "ruleset-private-key",
    "ruleset-credential",
    "public-key",
    "policy",
    "check-publisher-policy",
    "activation-selector-policy",
    "ruleset-observer-policy",
    "ruleset-public-key",
    "controller-principal-policy",
    "controller-start-policy",
    "post-activation-policy",
    "git-anchor-policy",
    "git-anchor-producer-policy",
    "git-anchor-github-private-key",
    "git-anchor-observer-private-key",
    "git-anchor-observer-public-key",
    "revocations",
    "authority-anchor",
    "issuer-service",
    "issuer-path",
    "receipt-service",
    "receipt-path",
    "request-service",
    "request-path",
    "activation-service",
    "activation-path",
    "check-worker-service",
    "check-worker-path",
    "selector-service",
    "selector-path",
    "selector-broker-service",
    "selector-broker-path",
    "activation-request-service",
    "activation-request-path",
    "controller-start-service",
    "controller-start-path",
    "post-activation-observer-service",
    "post-activation-observer-timer",
    "ruleset-observer-service",
    "ruleset-observer-timer",
    "ruleset-broker-service",
    "ruleset-broker-path",
    "git-anchor-updater-service",
    "git-anchor-updater-path",
    "git-anchor-job-broker-service",
    "git-anchor-job-broker-path",
    "git-anchor-producer-service",
    "git-anchor-producer-path",
    "git-anchor-promoter-service",
    "git-anchor-promoter-path",
    "activation-supervisor-service",
    "activation-supervisor-timer",
    "installed-controller-runtime-manifest",
    "controller-package-manifest",
    "controller-dependency-lock",
    "controller-runtime-environment",
    "controller-effective-config",
    "repository-snapshot",
    "repository-snapshot-manifest",
    "github-token-refresher",
    "github-token-refresher-policy",
    "github-token-refresher-private-key",
    "github-token-refresher-service",
    "github-token-refresher-timer",
    "github-token-promoter-service",
    "github-token-promoter-path",
    "deployment-refresh",
    "deployment-refresh-policy",
    "deployment-refresh-service",
    "deployment-refresh-path",
    "deployment-refresh-claim-service",
    "deployment-refresh-claim-path",
    "deployment-refresh-completion-service",
    "deployment-refresh-completion-path",
    "controller-service",
]

CANARY_IDS = (
    "real_claude_mechanical_task",
    "process_kill_and_resume",
    "quota_pause_and_resume",
    "authentication_expiry_and_recovery",
    "repeated_finding_finite_stop",
    "external_wait_lane_isolation",
    "bad_candidate_rejected_before_main",
    "release_transaction_crash_idempotency",
    "automatic_milestone_advancement",
    "machine_receipt_missing_invalid_expired_revoked",
    "duplicate_controller_rejection",
    "lease_renewal_failure",
    "stale_current_facts",
    "missing_source_authority",
    "malformed_report",
    "private_gate_missing_for_trust_risk",
    "machine_verifier_unavailable",
    "activation_receipt_wrong_sha",
    "runtime_root_outside_repo",
    "post_merge_invariant_failure_and_automated_revert_pr",
)
CANARY_DISTRIBUTION_FILES = (
    "__init__.py",
    "cli.py",
    "models.py",
    "runner.py",
    "mechanisms.py",
    "external_probes.py",
)

ROLE_TARGETS: dict[str, str] = {
    "public-verifier": "/usr/local/bin/traincapsule-verifier-verify-receipt",
    "reduction-oracle": "/usr/local/libexec/traincapsule-reduction-oracle",
    "reduction-oracle-public-key": (
        "/etc/traincapsule-verifier/keys/reduction-oracle.pub"
    ),
    "issuer": "/usr/libexec/traincapsule-verifier-issuer",
    "receipt-broker": "/usr/libexec/traincapsule-verifier-broker",
    "request-broker": "/usr/libexec/traincapsule-verifier-request-broker",
    "activation-issuer": "/usr/libexec/traincapsule-verifier-activation-issuer",
    "check-worker": "/usr/libexec/traincapsule-verifier-check-worker",
    "observed-main-selector": "/usr/libexec/traincapsule-verifier-observed-main-selector",
    "activation-selector-broker": "/usr/libexec/traincapsule-verifier-activation-selector-broker",
    "activation-request-broker": "/usr/libexec/traincapsule-verifier-activation-request-broker",
    "controller-start-broker": "/usr/libexec/traincapsule-verifier-controller-start",
    "post-activation-observer": "/usr/libexec/traincapsule-verifier-post-activation",
    "ruleset-observer": "/usr/libexec/traincapsule-verifier-ruleset-observer",
    "ruleset-broker": "/usr/libexec/traincapsule-verifier-ruleset-broker",
    "git-anchor-updater": "/usr/libexec/traincapsule-verifier-git-anchor-updater",
    "git-anchor-producer": "/usr/libexec/traincapsule-verifier-git-anchor-producer",
    "git-anchor-askpass": "/usr/libexec/traincapsule-anchor-askpass",
    "activation-supervisor-launcher": "/usr/libexec/traincapsule-activation-supervisor",
    "canary-runner": "/usr/local/bin/traincapsule-v31-run-canary",
    "canary-policy": "/etc/traincapsule-canary-runner/policy.json",
    "canary-live-probes-policy": "/etc/traincapsule-canary-runner/live-probes.json",
    "canary-receipt-probe": "/usr/libexec/traincapsule-verifier-canary-receipt-probe",
    "python-runtime": "/opt/traincapsule-runtime/python/bin/python3.12",
    "python-runtime-manifest": "/etc/traincapsule-runtime/runtime.json",
    "python-runtime-archive": "/opt/traincapsule-runtime/artifacts/python-runtime.zip",
    "python-runtime-distribution-manifest": (
        "/etc/traincapsule-runtime/python-distribution.json"
    ),
    "runtime-verifier-wheel": "/opt/traincapsule-runtime/wheels/verifier.whl",
    "runtime-controller-wheel": "/opt/traincapsule-runtime/wheels/controller.whl",
    "runtime-deployment-wheel": "/opt/traincapsule-runtime/wheels/deployment.whl",
    "runtime-canary-wheel": "/opt/traincapsule-runtime/wheels/canary-runner.whl",
    "runtime-pydantic-wheel": "/opt/traincapsule-runtime/wheels/pydantic.whl",
    "runtime-pydantic-core-wheel": "/opt/traincapsule-runtime/wheels/pydantic-core.whl",
    "runtime-typing-extensions-wheel": ("/opt/traincapsule-runtime/wheels/typing-extensions.whl"),
    "runtime-typing-inspection-wheel": ("/opt/traincapsule-runtime/wheels/typing-inspection.whl"),
    "runtime-cryptography-wheel": "/opt/traincapsule-runtime/wheels/cryptography.whl",
    "runtime-cffi-wheel": "/opt/traincapsule-runtime/wheels/cffi.whl",
    "runtime-pycparser-wheel": "/opt/traincapsule-runtime/wheels/pycparser.whl",
    "canary-claude-token": ("/var/lib/traincapsule-canary-secrets/claude-max-oauth-token"),
    "canary-claude-executable": "/usr/libexec/traincapsule-canary-claude",
    "canary-github-executable": "/usr/libexec/traincapsule-canary-github-client",
    "controller-oauth-token": (
        "/var/lib/traincapsule-controller/.config/traincapsule/claude-oauth-token"
    ),
    "external-evidence-broker": "/usr/local/bin/tcfactory-external-evidence-broker",
    "external-evidence-public-key": ("/etc/traincapsule-factory/external-evidence/authority.pub"),
    "external-evidence-revocations": (
        "/var/lib/traincapsule-external-evidence/staged-authority/revocation-list.json"
    ),
    "external-evidence-revocations-signature": (
        "/var/lib/traincapsule-external-evidence/staged-authority/revocation-list.json.sig"
    ),
    "external-evidence-authority-anchor": (
        "/var/lib/traincapsule-external-evidence/staged-authority/authority-anchor.json"
    ),
    "external-evidence-authority-anchor-signature": (
        "/var/lib/traincapsule-external-evidence/staged-authority/authority-anchor.json.sig"
    ),
    "external-evidence-service": (
        "/etc/systemd/system/traincapsule-external-evidence-authority.service"
    ),
    "external-evidence-path": ("/etc/systemd/system/traincapsule-external-evidence-authority.path"),
    "private-key": "/var/lib/traincapsule-verifier/private/signing-key.pem",
    "github-app-private-key": "/var/lib/traincapsule-verifier/github-app/private-key.pem",
    "selector-private-key": "/var/lib/traincapsule-verifier/selector-private/private-key.pem",
    "selector-credential": "/etc/traincapsule-verifier/selector-credential.env",
    "ruleset-private-key": "/var/lib/traincapsule-verifier/ruleset-private/private-key.pem",
    "ruleset-credential": "/etc/traincapsule-verifier/ruleset-observer-credential.env",
    "public-key": "/etc/traincapsule-verifier/public-key.pem",
    "policy": "/etc/traincapsule-verifier/policy.json",
    "machine-policy-review-profile": (
        "/etc/traincapsule-verifier/request-profiles/machine_policy_review.json"
    ),
    "activation-policy-profile": (
        "/etc/traincapsule-verifier/request-profiles/activation_policy.json"
    ),
    "check-publisher-policy": "/etc/traincapsule-verifier/check-publisher.json",
    "activation-selector-policy": "/etc/traincapsule-verifier/activation-selector.json",
    "ruleset-observer-policy": "/etc/traincapsule-verifier/ruleset-observer.json",
    "ruleset-public-key": "/etc/traincapsule-verifier/ruleset-public-key.pem",
    "controller-principal-policy": "/etc/traincapsule-verifier/controller-principal.json",
    "controller-start-policy": "/etc/traincapsule-verifier/controller-start-policy.json",
    "post-activation-policy": "/etc/traincapsule-verifier/post-activation-policy.json",
    "git-anchor-policy": "/etc/traincapsule-verifier/git-anchor-policy.json",
    "git-anchor-producer-policy": "/etc/traincapsule-verifier/git-anchor-producer-policy.json",
    "git-anchor-github-private-key": (
        "/var/lib/traincapsule-verifier/anchor-fetcher-private/github-app-private-key.pem"
    ),
    "git-anchor-observer-private-key": (
        "/var/lib/traincapsule-verifier/anchor-fetcher-private/observer-private-key.pem"
    ),
    "git-anchor-observer-public-key": (
        "/etc/traincapsule-verifier/anchor-observer-public-key.pem"
    ),
    "revocations": "/etc/traincapsule-verifier/revocations.json",
    "authority-anchor": "/etc/traincapsule-verifier/authority-anchor.json",
    "issuer-service": "/etc/systemd/system/traincapsule-verifier-issuer.service",
    "issuer-path": "/etc/systemd/system/traincapsule-verifier-issuer.path",
    "receipt-service": "/etc/systemd/system/traincapsule-verifier-broker.service",
    "receipt-path": "/etc/systemd/system/traincapsule-verifier-broker.path",
    "request-service": "/etc/systemd/system/traincapsule-verifier-request-broker.service",
    "request-path": "/etc/systemd/system/traincapsule-verifier-request-broker.path",
    "activation-service": "/etc/systemd/system/traincapsule-verifier-activation-issuer.service",
    "activation-path": "/etc/systemd/system/traincapsule-verifier-activation-issuer.path",
    "check-worker-service": "/etc/systemd/system/traincapsule-verifier-check-worker.service",
    "check-worker-path": "/etc/systemd/system/traincapsule-verifier-check-worker.path",
    "selector-service": "/etc/systemd/system/traincapsule-verifier-observed-main-selector.service",
    "selector-path": "/etc/systemd/system/traincapsule-verifier-observed-main-selector.path",
    "selector-broker-service": (
        "/etc/systemd/system/traincapsule-verifier-activation-selector-broker.service"
    ),
    "selector-broker-path": (
        "/etc/systemd/system/traincapsule-verifier-activation-selector-broker.path"
    ),
    "activation-request-service": (
        "/etc/systemd/system/traincapsule-verifier-activation-request-broker.service"
    ),
    "activation-request-path": (
        "/etc/systemd/system/traincapsule-verifier-activation-request-broker.path"
    ),
    "controller-start-service": (
        "/etc/systemd/system/traincapsule-verifier-controller-start.service"
    ),
    "controller-start-path": ("/etc/systemd/system/traincapsule-verifier-controller-start.path"),
    "post-activation-observer-service": (
        "/etc/systemd/system/traincapsule-verifier-post-activation-observer.service"
    ),
    "post-activation-observer-timer": (
        "/etc/systemd/system/traincapsule-verifier-post-activation-observer.timer"
    ),
    "ruleset-observer-service": (
        "/etc/systemd/system/traincapsule-verifier-ruleset-observer.service"
    ),
    "ruleset-observer-timer": ("/etc/systemd/system/traincapsule-verifier-ruleset-observer.timer"),
    "ruleset-broker-service": "/etc/systemd/system/traincapsule-verifier-ruleset-broker.service",
    "ruleset-broker-path": "/etc/systemd/system/traincapsule-verifier-ruleset-broker.path",
    "git-anchor-updater-service": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-updater.service"
    ),
    "git-anchor-updater-path": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-updater.path"
    ),
    "git-anchor-job-broker-service": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-job-broker.service"
    ),
    "git-anchor-job-broker-path": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-job-broker.path"
    ),
    "git-anchor-producer-service": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-producer.service"
    ),
    "git-anchor-producer-path": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-producer.path"
    ),
    "git-anchor-promoter-service": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-promoter.service"
    ),
    "git-anchor-promoter-path": (
        "/etc/systemd/system/traincapsule-verifier-git-anchor-promoter.path"
    ),
    "activation-supervisor-service": (
        "/etc/systemd/system/traincapsule-activation-supervisor.service"
    ),
    "activation-supervisor-timer": "/etc/systemd/system/traincapsule-activation-supervisor.timer",
    "installed-controller-runtime-manifest": (
        "/etc/traincapsule-controller/runtime-manifest.json"
    ),
    "controller-package-manifest": "/opt/traincapsule-runtime/package.json",
    "controller-dependency-lock": "/opt/traincapsule-runtime/dependency.lock",
    "controller-runtime-environment": (
        "/etc/traincapsule-controller/controller-runtime.env"
    ),
    "controller-effective-config": "/etc/traincapsule-controller/effective-config.yaml",
    "repository-snapshot": "/opt/traincapsule-runtime/repository-snapshot.zip",
    "repository-snapshot-manifest": (
        "/var/lib/traincapsule-verifier/repository-boundary/SNAPSHOT_MANIFEST.json"
    ),
    "github-token-refresher": "/usr/libexec/traincapsule-github-token-refresher",
    "github-token-refresher-policy": (
        "/etc/traincapsule-canary-runner/github-token-refresher.json"
    ),
    "github-token-refresher-private-key": (
        "/var/lib/traincapsule-github-token/github-app-private-key.pem"
    ),
    "github-token-refresher-service": (
        "/etc/systemd/system/traincapsule-github-token-refresher.service"
    ),
    "github-token-refresher-timer": (
        "/etc/systemd/system/traincapsule-github-token-refresher.timer"
    ),
    "github-token-promoter-service": (
        "/etc/systemd/system/traincapsule-github-token-promoter.service"
    ),
    "github-token-promoter-path": (
        "/etc/systemd/system/traincapsule-github-token-promoter.path"
    ),
    "deployment-refresh": "/usr/libexec/traincapsule-deployment-refresh",
    "deployment-refresh-policy": "/etc/traincapsule-deployment/refresh-policy.json",
    "deployment-refresh-service": (
        "/etc/systemd/system/traincapsule-deployment-refresh.service"
    ),
    "deployment-refresh-path": (
        "/etc/systemd/system/traincapsule-deployment-refresh.path"
    ),
    "deployment-refresh-claim-service": (
        "/etc/systemd/system/traincapsule-deployment-refresh-claim.service"
    ),
    "deployment-refresh-claim-path": (
        "/etc/systemd/system/traincapsule-deployment-refresh-claim.path"
    ),
    "deployment-refresh-completion-service": (
        "/etc/systemd/system/traincapsule-deployment-refresh-completion.service"
    ),
    "deployment-refresh-completion-path": (
        "/etc/systemd/system/traincapsule-deployment-refresh-completion.path"
    ),
    "controller-service": "/etc/systemd/system/traincapsule-controller.service",
}
ROLE_TARGETS.update(
    {
        f"canary-{canary_id}": f"/usr/libexec/traincapsule-canary-{canary_id}"
        for canary_id in CANARY_IDS
    }
)
ROLE_TARGETS.update(
    {
        f"canary-distribution-{name[:-3].replace('_', '-')}": (
            "/opt/traincapsule-canary-runner/lib/python3.12/site-packages/"
            f"traincapsule_canary_runner/{name}"
        )
        for name in CANARY_DISTRIBUTION_FILES
    }
)
PATH_UNITS = (
    "traincapsule-external-evidence-authority.path",
    "traincapsule-verifier-request-broker.path",
    "traincapsule-verifier-issuer.path",
    "traincapsule-verifier-ruleset-observer.timer",
    "traincapsule-verifier-ruleset-broker.path",
    "traincapsule-verifier-git-anchor-updater.path",
    "traincapsule-verifier-git-anchor-job-broker.path",
    "traincapsule-verifier-git-anchor-producer.path",
    "traincapsule-verifier-git-anchor-promoter.path",
    "traincapsule-verifier-activation-request-broker.path",
    "traincapsule-verifier-controller-start.path",
    "traincapsule-verifier-post-activation-observer.timer",
    "traincapsule-github-token-promoter.path",
    "traincapsule-github-token-refresher.timer",
    "traincapsule-deployment-refresh.path",
    "traincapsule-deployment-refresh-claim.path",
    "traincapsule-deployment-refresh-completion.path",
    "traincapsule-verifier-observed-main-selector.path",
    "traincapsule-verifier-activation-selector-broker.path",
    "traincapsule-verifier-activation-issuer.path",
    "traincapsule-verifier-broker.path",
    "traincapsule-verifier-check-worker.path",
    "traincapsule-activation-supervisor.timer",
)


class InstallFailure(RuntimeError):
    """A fail-closed preflight, installation, or attestation failure."""


class LockedAccount(StrictModel):
    name: str = Field(pattern=r"^[a-z_][a-z0-9_-]{2,31}$")
    home: str
    shell: Literal["/usr/sbin/nologin", "/sbin/nologin"] = "/usr/sbin/nologin"


class DirectoryPin(StrictModel):
    target: str
    owner: str
    group: str
    mode: str = Field(pattern=r"^0[0-7]{3}$")


class FilePin(StrictModel):
    role: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,95}$")
    source: str
    target: str
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    owner: str
    group: str
    mode: str = Field(pattern=r"^0[0-7]{3}$")


class SnapshotEntry(StrictModel):
    path: str = Field(pattern=r"^[^/\x00\r\n][^\x00\r\n]{0,4094}$")
    kind: Literal["directory", "file"]
    mode: str = Field(pattern=r"^0[0-7]{3}$")
    digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_kind(self) -> SnapshotEntry:
        pure = PurePosixPath(self.path)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != self.path:
            raise ValueError("snapshot entry path is not normalized")
        if (self.kind == "file") != (self.digest is not None):
            raise ValueError("only snapshot files have content digests")
        if (self.kind == "directory" and self.mode != "0555") or (
            self.kind == "file" and self.mode not in {"0444", "0555"}
        ):
            raise ValueError("snapshot entries must be immutable")
        if self.path == "SNAPSHOT_MANIFEST.json":
            raise ValueError("snapshot manifest cannot inventory itself")
        return self


class SnapshotGitObject(StrictModel):
    object_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    kind: Literal["blob", "tree", "commit", "tag"]
    size: int = Field(ge=0, le=2_000_000_000)


class RepositorySnapshotManifest(StrictModel):
    schema_version: Literal["3.1"] = "3.1"
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_manifest_path: str
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_config_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    python_runtime_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    package_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_lock_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    entries: list[SnapshotEntry]
    git_objects: list[SnapshotGitObject]

    @model_validator(mode="after")
    def exact_inventory(self) -> RepositorySnapshotManifest:
        paths = [entry.path for entry in self.entries]
        objects = [item.object_id for item in self.git_objects]
        source = PurePosixPath(self.source_manifest_path)
        if (
            not self.entries
            or not self.git_objects
            or paths != sorted(paths)
            or len(paths) != len(set(paths))
            or objects != sorted(objects)
            or len(objects) != len(set(objects))
            or source.is_absolute()
            or ".." in source.parts
            or str(source) != self.source_manifest_path
            or self.source_manifest_path not in paths
        ):
            raise ValueError("repository snapshot inventory is not exact")
        payload = self.model_dump(mode="json", by_alias=True)
        payload["manifestDigest"] = "sha256:" + "0" * 64
        if self.manifest_digest != sha256_digest(canonical_json_bytes(payload)):
            raise ValueError("repository snapshot manifest digest mismatch")
        return self


class PrivilegedInstallSpec(StrictModel):
    """Self-digesting, exact allow-listed distribution lock."""

    schema_version: Literal["3.1"] = "3.1"
    state: Literal["STAGED_NOT_INSTALLED"] = "STAGED_NOT_INSTALLED"
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    service_account: LockedAccount
    selector_account: LockedAccount
    ruleset_account: LockedAccount
    token_refresher_account: LockedAccount
    anchor_fetcher_account: LockedAccount
    controller_account: LockedAccount
    directories: list[DirectoryPin]
    files: list[FilePin]
    controller_unit: Literal["traincapsule-controller.service"]
    path_units: list[str]
    generates_credentials: Literal[False] = False
    generates_receipts: Literal[False] = False
    runs_oracles: Literal[False] = False

    @model_validator(mode="after")
    def exact_boundary(self) -> PrivilegedInstallSpec:
        if self.service_account.name != SERVICE_USER:
            raise ValueError("service account name is fixed")
        if self.selector_account.name != SELECTOR_USER:
            raise ValueError("selector account name is fixed")
        if self.ruleset_account.name != RULESET_USER:
            raise ValueError("ruleset observer account name is fixed")
        if self.token_refresher_account.name != TOKEN_REFRESHER_USER:
            raise ValueError("GitHub token refresher account name is fixed")
        if self.anchor_fetcher_account.name != ANCHOR_FETCHER_USER:
            raise ValueError("Git anchor fetcher account name is fixed")
        if self.controller_account.name != DEFAULT_CONTROLLER_USER:
            raise ValueError("controller account name is fixed to the dedicated principal")
        roles = [item.role for item in self.files]
        core_roles = set(ROLE_TARGETS)
        if not core_roles <= set(roles) or len(roles) != len(set(roles)):
            raise ValueError("every core install role must appear exactly once")
        oracle_files = [item for item in self.files if item.role not in core_roles]
        if not oracle_files or any(not item.role.startswith("oracle-") for item in oracle_files):
            raise ValueError("one or more explicitly pinned oracle executables are required")
        for item in self.files:
            expected_target = ROLE_TARGETS.get(item.role)
            if expected_target is not None and item.target != expected_target:
                raise ValueError(f"target for {item.role} is not allow-listed")
            if item.role not in ROLE_TARGETS:
                pure = PurePosixPath(item.target)
                if (
                    not pure.is_absolute()
                    or ".." in pure.parts
                    or not item.target.startswith("/var/lib/traincapsule-verifier/oracle/")
                    or (item.owner, item.group, item.mode) != (SERVICE_USER, SERVICE_USER, "0500")
                ):
                    raise ValueError("oracle runner target or metadata is unsafe")
        if tuple(self.path_units) != PATH_UNITS:
            raise ValueError("path unit activation order is fixed")
        _validate_directories(self)
        _validate_role_metadata(self)
        payload = self.model_dump(mode="json", by_alias=True)
        payload["manifestDigest"] = "sha256:" + "0" * 64
        if self.manifest_digest != sha256_digest(canonical_json_bytes(payload)):
            raise ValueError("installer manifest digest mismatch")
        return self


class DeploymentAttestation(StrictModel):
    schema_version: Literal["3.1"] = "3.1"
    state: Literal["FILES_ATTESTED", "PATH_UNITS_ENABLED"]
    manifest_digest: str
    controller_principal: str
    controller_runtime_bound: Literal[False] = False
    controller_service_stopped: Literal[True] = True
    checked_directories: int
    checked_files: int
    negative_access_checks: int
    path_units_enabled: bool
    authority_receipt_issued: Literal[False] = False
    activation_receipt_issued: Literal[False] = False
    oracle_outcome_claimed: Literal[False] = False


def _validate_role_metadata(spec: PrivilegedInstallSpec) -> None:
    by_role = {item.role: item for item in spec.files}
    public = by_role["public-verifier"]
    if (public.owner, public.group, public.mode) != ("root", "root", "0755"):
        raise ValueError("public verifier must be root-owned and publicly executable")
    reduction_oracle = by_role["reduction-oracle"]
    if (
        reduction_oracle.owner,
        reduction_oracle.group,
        reduction_oracle.mode,
    ) != ("root", "root", "0555"):
        raise ValueError("reduction oracle must be root-owned and immutable")
    reduction_key = by_role["reduction-oracle-public-key"]
    if (reduction_key.owner, reduction_key.group, reduction_key.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("reduction oracle public key must be root-owned and immutable")
    for role in ("issuer", "activation-issuer", "check-worker"):
        issuer = by_role[role]
        if (issuer.owner, issuer.group, issuer.mode) != ("root", SERVICE_USER, "0750"):
            raise ValueError(
                "private workers must be executable only by root and the issuer account"
            )
    for role in ("receipt-broker", "request-broker"):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != ("root", "root", "0700"):
            raise ValueError("root brokers must not be executable by either service account")
    selector = by_role["observed-main-selector"]
    if (selector.owner, selector.group, selector.mode) != ("root", SELECTOR_USER, "0750"):
        raise ValueError("selector binary must be executable only by its account")
    selector_broker = by_role["activation-selector-broker"]
    if (selector_broker.owner, selector_broker.group, selector_broker.mode) != (
        "root",
        "root",
        "0700",
    ):
        raise ValueError("selector broker must be root-only")
    ruleset_observer = by_role["ruleset-observer"]
    if (ruleset_observer.owner, ruleset_observer.group, ruleset_observer.mode) != (
        "root",
        RULESET_USER,
        "0750",
    ):
        raise ValueError("ruleset observer binary must be restricted to its account")
    for role in (
        "activation-request-broker",
        "ruleset-broker",
        "controller-start-broker",
        "post-activation-observer",
        "git-anchor-updater",
        "deployment-refresh",
    ):
        broker = by_role[role]
        if (broker.owner, broker.group, broker.mode) != ("root", "root", "0700"):
            raise ValueError("authority copy brokers must be root-only")
    refresher = by_role["github-token-refresher"]
    if (refresher.owner, refresher.group, refresher.mode) != (
        "root",
        TOKEN_REFRESHER_USER,
        "0750",
    ):
        raise ValueError("GitHub token refresher executable access is unsafe")
    refresher_policy = by_role["github-token-refresher-policy"]
    if (refresher_policy.owner, refresher_policy.group, refresher_policy.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("GitHub token refresher policy must be immutable")
    refresher_key = by_role["github-token-refresher-private-key"]
    if (refresher_key.owner, refresher_key.group, refresher_key.mode) != (
        TOKEN_REFRESHER_USER,
        TOKEN_REFRESHER_USER,
        "0600",
    ):
        raise ValueError("GitHub token refresher key must be refresher-only")
    refresh_policy = by_role["deployment-refresh-policy"]
    if (refresh_policy.owner, refresh_policy.group, refresh_policy.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("deployment refresh policy must be immutable")
    for role in ("git-anchor-producer", "git-anchor-askpass"):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != (
            "root",
            ANCHOR_FETCHER_USER,
            "0750",
        ):
            raise ValueError("Git anchor producer executables must be fetcher-restricted")
    for role in ("git-anchor-github-private-key", "git-anchor-observer-private-key"):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != (
            ANCHOR_FETCHER_USER,
            ANCHOR_FETCHER_USER,
            "0600",
        ):
            raise ValueError("Git anchor producer keys must be fetcher-only")
    for role in ("git-anchor-producer-policy", "git-anchor-observer-public-key"):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != ("root", "root", "0444"):
            raise ValueError("Git anchor producer public inputs must be immutable")
    supervisor = by_role["activation-supervisor-launcher"]
    controller = spec.controller_account.name
    if (supervisor.owner, supervisor.group, supervisor.mode) != (
        "root",
        controller,
        "0750",
    ):
        raise ValueError("activation supervisor must be restricted to the controller principal")
    runner = by_role["canary-runner"]
    if (runner.owner, runner.group, runner.mode) != ("root", "root", "0555"):
        raise ValueError("canary runner must be root-owned and immutable")
    canary_policy = by_role["canary-policy"]
    if (canary_policy.owner, canary_policy.group, canary_policy.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("canary policy must be root-owned and immutable")
    live_policy = by_role["canary-live-probes-policy"]
    if (live_policy.owner, live_policy.group, live_policy.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("live canary policy must be root-owned and immutable")
    receipt_probe = by_role["canary-receipt-probe"]
    if (receipt_probe.owner, receipt_probe.group, receipt_probe.mode) != (
        "root",
        "root",
        "0555",
    ):
        raise ValueError("canary receipt probe must be root-owned and immutable")
    python_runtime = by_role["python-runtime"]
    if (python_runtime.owner, python_runtime.group, python_runtime.mode) != (
        "root",
        "root",
        "0555",
    ):
        raise ValueError("Python runtime must be root-owned and immutable")
    python_manifest = by_role["python-runtime-manifest"]
    if (python_manifest.owner, python_manifest.group, python_manifest.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("Python runtime manifest must be root-owned and immutable")
    for role in ("python-runtime-archive", "python-runtime-distribution-manifest"):
        artifact = by_role[role]
        if (artifact.owner, artifact.group, artifact.mode) != ("root", "root", "0444"):
            raise ValueError("Python runtime distribution must be root-owned and immutable")
    for role in (
        "runtime-verifier-wheel",
        "runtime-controller-wheel",
        "runtime-deployment-wheel",
        "runtime-canary-wheel",
        "runtime-pydantic-wheel",
        "runtime-pydantic-core-wheel",
        "runtime-typing-extensions-wheel",
        "runtime-typing-inspection-wheel",
    ):
        wheel = by_role[role]
        if (wheel.owner, wheel.group, wheel.mode) != ("root", "root", "0444"):
            raise ValueError("offline runtime wheels must be root-owned and immutable")
    for role in ("canary-claude-executable", "canary-github-executable"):
        executable = by_role[role]
        if (executable.owner, executable.group, executable.mode) != (
            "root",
            "root",
            "0555",
        ):
            raise ValueError("live canary executables must be root-owned and immutable")
    for name in CANARY_DISTRIBUTION_FILES:
        role = f"canary-distribution-{name[:-3].replace('_', '-')}"
        source = by_role[role]
        if (source.owner, source.group, source.mode) != ("root", "root", "0444"):
            raise ValueError("canary distribution sources must be root-owned and immutable")
    token = by_role["canary-claude-token"]
    if (token.owner, token.group, token.mode) != (controller, controller, "0400"):
        raise ValueError("live canary credentials must be controller-only")
    for canary_id in CANARY_IDS:
        mechanism = by_role[f"canary-{canary_id}"]
        if (mechanism.owner, mechanism.group, mechanism.mode) != (
            "root",
            "root",
            "0555",
        ):
            raise ValueError("canary mechanisms must be root-owned and immutable")
    oauth = by_role["controller-oauth-token"]
    if (oauth.owner, oauth.group, oauth.mode) != (controller, controller, "0600"):
        raise ValueError("controller OAuth token must be controller-only")
    broker = by_role["external-evidence-broker"]
    if (broker.owner, broker.group, broker.mode) != ("root", "root", "0755"):
        raise ValueError("external-evidence broker must be root-owned")
    public_key = by_role["external-evidence-public-key"]
    if (public_key.owner, public_key.group, public_key.mode) != (
        "root",
        "root",
        "0444",
    ):
        raise ValueError("external-evidence public key must be immutable")
    for role in ("external-evidence-service", "external-evidence-path"):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != ("root", "root", "0644"):
            raise ValueError("external-evidence public configuration is unsafe")
    for role in (
        "external-evidence-revocations",
        "external-evidence-revocations-signature",
        "external-evidence-authority-anchor",
        "external-evidence-authority-anchor-signature",
    ):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != ("root", "root", "0400"):
            raise ValueError("staged authority snapshots must be root-only")
    for role in ("private-key", "github-app-private-key"):
        private = by_role[role]
        if (private.owner, private.group, private.mode) != (SERVICE_USER, SERVICE_USER, "0600"):
            raise ValueError("private key ownership or mode is unsafe")
    for role in ("selector-private-key", "selector-credential"):
        private = by_role[role]
        if (private.owner, private.group, private.mode) != (SELECTOR_USER, SELECTOR_USER, "0600"):
            raise ValueError("selector credentials must be selector-only")
    for role in ("ruleset-private-key", "ruleset-credential"):
        private = by_role[role]
        if (private.owner, private.group, private.mode) != (
            RULESET_USER,
            RULESET_USER,
            "0600",
        ):
            raise ValueError("ruleset observer credentials must be observer-only")
    for role in (
        "public-key",
        "policy",
        "machine-policy-review-profile",
        "activation-policy-profile",
        "check-publisher-policy",
        "activation-selector-policy",
        "ruleset-observer-policy",
        "ruleset-public-key",
        "controller-principal-policy",
        "controller-start-policy",
        "post-activation-policy",
        "git-anchor-policy",
        "revocations",
        "authority-anchor",
    ):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != ("root", "root", "0644"):
            raise ValueError("public authority files must be root-owned read-only")
    for role in (
        "issuer-service",
        "issuer-path",
        "receipt-service",
        "receipt-path",
        "request-service",
        "request-path",
        "activation-service",
        "activation-path",
        "check-worker-service",
        "check-worker-path",
        "selector-service",
        "selector-path",
        "selector-broker-service",
        "selector-broker-path",
        "activation-request-service",
        "activation-request-path",
        "controller-start-service",
        "controller-start-path",
        "post-activation-observer-service",
        "post-activation-observer-timer",
        "ruleset-observer-service",
        "ruleset-observer-timer",
        "ruleset-broker-service",
        "ruleset-broker-path",
        "git-anchor-updater-service",
        "git-anchor-updater-path",
        "git-anchor-job-broker-service",
        "git-anchor-job-broker-path",
        "git-anchor-producer-service",
        "git-anchor-producer-path",
        "git-anchor-promoter-service",
        "git-anchor-promoter-path",
        "activation-supervisor-service",
        "activation-supervisor-timer",
        "controller-service",
        "github-token-refresher-service",
        "github-token-refresher-timer",
        "github-token-promoter-service",
        "github-token-promoter-path",
        "deployment-refresh-service",
        "deployment-refresh-path",
        "deployment-refresh-claim-service",
        "deployment-refresh-claim-path",
        "deployment-refresh-completion-service",
        "deployment-refresh-completion-path",
    ):
        item = by_role[role]
        if (item.owner, item.group, item.mode) != ("root", "root", "0644"):
            raise ValueError("systemd units must be root-owned 0644")
    for role in (
        "installed-controller-runtime-manifest",
        "controller-package-manifest",
        "controller-dependency-lock",
        "controller-runtime-environment",
        "controller-effective-config",
        "repository-snapshot",
        "repository-snapshot-manifest",
    ):
        artifact = by_role[role]
        if (artifact.owner, artifact.group, artifact.mode) != ("root", "root", "0444"):
            raise ValueError("controller runtime artifacts must be root-owned and immutable")


def _validate_directories(spec: PrivilegedInstallSpec) -> None:
    expected = production_directory_pins(
        service_account=spec.service_account,
        selector_account=spec.selector_account,
        ruleset_account=spec.ruleset_account,
        token_refresher_account=spec.token_refresher_account,
        anchor_fetcher_account=spec.anchor_fetcher_account,
        controller_account=spec.controller_account,
    )
    required = {item.target: (item.owner, item.group, item.mode) for item in expected}
    actual = {item.target: (item.owner, item.group, item.mode) for item in spec.directories}
    if actual != required or len(actual) != len(spec.directories):
        raise ValueError("managed directory set or metadata is not exact")
    seen: set[str] = set()
    for item in spec.directories:
        parent = str(PurePosixPath(item.target).parent)
        if parent in required and parent not in seen:
            raise ValueError("managed parent directories must precede their children")
        seen.add(item.target)


def production_directory_pins(
    *,
    service_account: LockedAccount,
    selector_account: LockedAccount,
    ruleset_account: LockedAccount,
    token_refresher_account: LockedAccount,
    anchor_fetcher_account: LockedAccount,
    controller_account: LockedAccount,
) -> list[DirectoryPin]:
    """Return the one accepted managed-directory topology in parent-first order."""

    service = service_account.name
    selector = selector_account.name
    ruleset = ruleset_account.name
    refresher = token_refresher_account.name
    fetcher = anchor_fetcher_account.name
    controller = controller_account.name
    rows = [
        ("/usr/local/libexec", "root", "root", "0755"),
        ("/var/lib/traincapsule-verifier", "root", "root", "0755"),
        ("/etc/traincapsule-verifier", "root", "root", "0755"),
        ("/etc/traincapsule-verifier/keys", "root", "root", "0755"),
        ("/etc/traincapsule-verifier/request-profiles", "root", "root", "0755"),
        ("/etc/traincapsule-canary-runner", "root", "root", "0755"),
        ("/etc/traincapsule-runtime", "root", "root", "0755"),
        ("/etc/traincapsule-controller", "root", "root", "0755"),
        ("/etc/traincapsule-deployment", "root", "root", "0755"),
        ("/var/lib/traincapsule-github-token", refresher, refresher, "0700"),
        ("/var/lib/traincapsule-github-token/outbox", refresher, refresher, "0700"),
        ("/var/lib/traincapsule-verifier/anchor-fetcher-inbox", fetcher, fetcher, "0700"),
        ("/var/lib/traincapsule-verifier/anchor-fetcher-outbox", fetcher, fetcher, "0700"),
        ("/var/lib/traincapsule-verifier/anchor-fetcher-private", fetcher, fetcher, "0700"),
        ("/opt/traincapsule-runtime", "root", "root", "0755"),
        ("/opt/traincapsule-runtime/artifacts", "root", "root", "0755"),
        ("/opt/traincapsule-runtime/wheels", "root", "root", "0755"),
        ("/opt/traincapsule-runtime/generations", "root", "root", "0555"),
        ("/opt/traincapsule-canary-runner", "root", "root", "0755"),
        ("/opt/traincapsule-canary-runner/lib", "root", "root", "0755"),
        ("/opt/traincapsule-canary-runner/lib/python3.12", "root", "root", "0755"),
        (
            "/opt/traincapsule-canary-runner/lib/python3.12/site-packages",
            "root",
            "root",
            "0755",
        ),
        (
            "/opt/traincapsule-canary-runner/lib/python3.12/site-packages/"
            "traincapsule_canary_runner",
            "root",
            "root",
            "0755",
        ),
        (
            "/var/lib/traincapsule-canary-secrets",
            controller,
            controller,
            "0700",
        ),
        ("/var/lib/traincapsule-runtime", controller, controller, "0700"),
        ("/var/lib/traincapsule-runtime/git", controller, controller, "0700"),
        ("/var/lib/traincapsule-runtime/worktrees", controller, controller, "0700"),
        ("/var/lib/traincapsule-runtime/artifacts", controller, controller, "0700"),
        ("/var/lib/traincapsule-runtime/artifacts/v3", controller, controller, "0700"),
        (
            "/var/lib/traincapsule-runtime/deployment-update-handoffs",
            controller,
            controller,
            "0700",
        ),
        ("/var/lib/traincapsule-verifier/anchor-update-journal", "root", "root", "0700"),
        (
            "/var/lib/traincapsule-verifier/deployment-refresh-claims",
            "root",
            "root",
            "0700",
        ),
        (
            "/var/lib/traincapsule-verifier/activation-refresh-inbox",
            "root",
            controller,
            "0750",
        ),
        (
            "/var/lib/traincapsule-verifier/activation-refresh-retirement",
            "root",
            "root",
            "0700",
        ),
        (
            "/var/lib/traincapsule-verifier/deployment-refresh-journal",
            "root",
            "root",
            "0700",
        ),
        (controller_account.home, controller, controller, "0700"),
        (f"{controller_account.home}/.config", controller, controller, "0700"),
        (
            f"{controller_account.home}/.config/traincapsule",
            controller,
            controller,
            "0700",
        ),
        ("/etc/traincapsule-factory", "root", "root", "0755"),
        ("/etc/traincapsule-factory/external-evidence", "root", "root", "0755"),
        ("/var/lib/traincapsule-external-evidence", "root", "root", "0755"),
        (
            "/var/lib/traincapsule-external-evidence/staged-authority",
            "root",
            "root",
            "0700",
        ),
        ("/var/lib/traincapsule-external-evidence-authority", "root", "root", "0755"),
        ("/var/lib/traincapsule-verifier/repository-boundary", "root", "root", "0555"),
        ("/var/lib/traincapsule-verifier/anchor-updates", "root", "root", "0700"),
        ("/var/lib/traincapsule-verifier/state", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/private", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/github-app", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/selector-private", selector, selector, "0700"),
        ("/var/lib/traincapsule-verifier/selector-outbox", selector, selector, "0700"),
        ("/var/lib/traincapsule-verifier/activation-requests", selector, selector, "0700"),
        ("/var/lib/traincapsule-verifier/ruleset-private", ruleset, ruleset, "0700"),
        ("/var/lib/traincapsule-verifier/ruleset-outbox", ruleset, ruleset, "0700"),
        ("/var/lib/traincapsule-verifier/ruleset", "root", "root", "0755"),
        ("/var/lib/traincapsule-verifier/oracle", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/outbox", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/inbox", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/activation-inbox", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/check-journal", service, service, "0700"),
        ("/var/lib/traincapsule-verifier/controller-outbox", controller, controller, "0700"),
        (
            "/var/lib/traincapsule-verifier/activation-controller-outbox",
            controller,
            controller,
            "0700",
        ),
        (
            "/var/lib/traincapsule-verifier/controller-start-outbox",
            controller,
            controller,
            "0700",
        ),
        (
            "/var/lib/traincapsule-verifier/controller-start-journal",
            "root",
            "root",
            "0700",
        ),
        (
            "/var/lib/traincapsule-verifier/post-activation-observations",
            "root",
            "root",
            "0700",
        ),
        ("/var/lib/traincapsule-verifier/activation", "root", "root", "0755"),
        ("/var/lib/traincapsule-verifier/request-journal", "root", "root", "0700"),
        ("/var/lib/traincapsule-verifier/receipts", "root", "root", "0755"),
        ("/var/lib/traincapsule-verifier/journal", "root", "root", "0700"),
    ]
    return [
        DirectoryPin(target=target, owner=owner, group=group, mode=mode)
        for target, owner, group, mode in rows
    ]


def unsigned_manifest_digest(payload: dict[str, object]) -> str:
    """Return the non-authority manifest lock; this is not a receipt or signature."""

    copy = dict(payload)
    copy["manifestDigest"] = "sha256:" + "0" * 64
    return sha256_digest(canonical_json_bytes(copy))


def load_repository_snapshot_manifest(path: Path) -> RepositorySnapshotManifest:
    try:
        raw = path.read_bytes()
        manifest = RepositorySnapshotManifest.model_validate_json(raw, strict=True)
    except (OSError, ValueError) as exc:
        raise InstallFailure("repository snapshot manifest is invalid") from exc
    if canonical_json_bytes(manifest) != raw:
        raise InstallFailure("repository snapshot manifest is not canonical")
    return manifest


def validate_repository_snapshot_archive(
    archive_path: Path, manifest: RepositorySnapshotManifest
) -> None:
    """Validate the complete deterministic, loose-object Git snapshot archive."""

    expected = {entry.path: entry for entry in manifest.entries}
    observed: dict[str, SnapshotEntry] = {}
    observed_order: list[str] = []
    objects: list[SnapshotGitObject] = []
    control_bytes: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if archive.comment:
                raise InstallFailure("snapshot archive comment is forbidden")
            for info in archive.infolist():
                if (
                    info.flag_bits & 0x1
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.date_time != (1980, 1, 1, 0, 0, 0)
                    or info.extra
                    or info.comment
                ):
                    raise InstallFailure("snapshot archive metadata is not deterministic")
                name = info.filename.removesuffix("/")
                pure = PurePosixPath(name)
                if (
                    not name
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or str(pure) != name
                    or name in observed
                ):
                    raise InstallFailure("snapshot archive path is unsafe or duplicated")
                unix_mode = info.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                directory = info.is_dir()
                if directory and file_type not in {0, stat.S_IFDIR}:
                    raise InstallFailure("snapshot directory metadata is unsafe")
                if not directory and file_type not in {0, stat.S_IFREG}:
                    raise InstallFailure("snapshot file is not a regular file")
                raw = b"" if directory else archive.read(info)
                entry = SnapshotEntry(
                    path=name,
                    kind="directory" if directory else "file",
                    mode=f"0{stat.S_IMODE(unix_mode):03o}",
                    digest=None if directory else sha256_digest(raw),
                )
                observed[name] = entry
                observed_order.append(name)
                if name in {".git/config", ".git/HEAD", ".git/refs/heads/main"}:
                    control_bytes[name] = raw
                match = re_full_git_object_path(name)
                if match is not None:
                    try:
                        unpacked = zlib.decompress(raw)
                        header, content = unpacked.split(b"\0", 1)
                        kind_raw, size_raw = header.split(b" ", 1)
                        kind = kind_raw.decode("ascii")
                        size = int(size_raw)
                    except (UnicodeDecodeError, ValueError, zlib.error) as exc:
                        raise InstallFailure("snapshot Git object is malformed") from exc
                    object_id = match
                    if (
                        kind not in {"blob", "tree", "commit", "tag"}
                        or size != len(content)
                        or hashlib.sha1(unpacked, usedforsecurity=False).hexdigest() != object_id
                    ):
                        raise InstallFailure("snapshot Git object identity mismatch")
                    object_kind = cast(Literal["blob", "tree", "commit", "tag"], kind)
                    objects.append(
                        SnapshotGitObject(object_id=object_id, kind=object_kind, size=size)
                    )
    except (OSError, zipfile.BadZipFile) as exc:
        raise InstallFailure("repository snapshot archive is invalid") from exc
    if observed != expected:
        raise InstallFailure("snapshot archive does not match its complete inventory")
    if observed_order != [entry.path for entry in manifest.entries]:
        raise InstallFailure("snapshot archive order is not deterministic")
    if sorted(objects, key=lambda item: item.object_id) != manifest.git_objects:
        raise InstallFailure("snapshot Git object inventory mismatch")
    source = observed.get(manifest.source_manifest_path)
    if source is None or source.digest != manifest.source_generation_digest:
        raise InstallFailure("snapshot source-generation binding mismatch")
    git_config = control_bytes.get(".git/config", b"").lower()
    if (
        control_bytes.get(".git/HEAD") != b"ref: refs/heads/main\n"
        or control_bytes.get(".git/refs/heads/main") != (manifest.main_sha + "\n").encode()
        or not git_config
        or any(
            forbidden in git_config
            for forbidden in (
                b"[remote",
                b"[credential",
                b"[http",
                b"[url",
                b"[include",
                b"alternate",
            )
        )
    ):
        raise InstallFailure("snapshot Git HEAD/ref/config binding is unsafe")
    if (
        any(
            path.startswith(".git/objects/pack/") and entry.kind == "file"
            for path, entry in observed.items()
        )
        or ".git/objects/info/alternates" in observed
        or any(path.startswith(".git/hooks/") for path in observed)
    ):
        raise InstallFailure("snapshot has packed, alternate, or hook-based Git behavior")


def re_full_git_object_path(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if (
        len(parts) == 4
        and parts[:2] == (".git", "objects")
        and len(parts[2]) == 2
        and len(parts[3]) == 38
        and all(character in "0123456789abcdef" for character in parts[2] + parts[3])
    ):
        return parts[2] + parts[3]
    return None


class AuthorityBackend(Protocol):
    simulated: bool

    def ensure_locked(self, account: LockedAccount) -> bool: ...
    def uid(self, name: str) -> int: ...
    def gid(self, name: str) -> int: ...
    def groups(self, name: str) -> set[int]: ...
    def owner(self, path: Path) -> tuple[int, int]: ...
    def chown(self, path: Path, user: str, group: str) -> None: ...
    def restore_owner(self, path: Path, uid: int, gid: int) -> None: ...


class SystemBackend(Protocol):
    simulated: bool

    def system_ready(self) -> bool: ...
    def unit_enabled(self, unit: str) -> bool: ...
    def unit_active(self, unit: str) -> bool: ...
    def unit_main_pid(self, unit: str) -> int: ...
    def daemon_reload(self) -> None: ...
    def enable_unit(self, unit: str) -> None: ...
    def disable_unit(self, unit: str) -> None: ...
    def start_unit(self, unit: str) -> None: ...
    def stop_unit(self, unit: str) -> None: ...
    def restart_unit(self, unit: str) -> None: ...


class LinuxAuthority:
    simulated = False

    def ensure_locked(self, account: LockedAccount) -> bool:
        try:
            entry = pwd.getpwnam(account.name)
        except KeyError:
            subprocess.run(
                [
                    "useradd",
                    "--system",
                    "--user-group",
                    "--home-dir",
                    account.home,
                    "--shell",
                    account.shell,
                    "--no-create-home",
                    account.name,
                ],
                check=True,
            )
            entry = pwd.getpwnam(account.name)
            created = True
        else:
            created = False
        if entry.pw_uid == 0 or entry.pw_dir != account.home or entry.pw_shell != account.shell:
            raise InstallFailure(
                f"existing account {account.name} is not the locked account requested"
            )
        status = subprocess.run(
            ["passwd", "--status", account.name], check=True, capture_output=True, text=True
        ).stdout.split()
        if len(status) < 2 or status[1] not in {"L", "LK"}:
            raise InstallFailure(f"account {account.name} is not password-locked")
        return created

    def uid(self, name: str) -> int:
        return pwd.getpwnam(name).pw_uid if name != "root" else 0

    def gid(self, name: str) -> int:
        return grp.getgrnam(name).gr_gid if name != "root" else 0

    def groups(self, name: str) -> set[int]:
        entry = pwd.getpwnam(name)
        values = {entry.pw_gid}
        values.update(item.gr_gid for item in grp.getgrall() if name in item.gr_mem)
        return values

    def owner(self, path: Path) -> tuple[int, int]:
        value = path.lstat()
        return value.st_uid, value.st_gid

    def chown(self, path: Path, user: str, group: str) -> None:
        os.chown(path, self.uid(user), self.gid(group), follow_symlinks=False)

    def restore_owner(self, path: Path, uid: int, gid: int) -> None:
        os.chown(path, uid, gid, follow_symlinks=False)


class LinuxSystemd:
    simulated = False

    def system_ready(self) -> bool:
        if not Path("/run/systemd/system").is_dir():
            return False
        return (
            subprocess.run(
                ["systemctl", "show", "--property=Version", "--value"],
                check=False,
                capture_output=True,
                text=True,
            ).returncode
            == 0
        )

    @staticmethod
    def _show(unit: str, prop: str) -> str:
        return subprocess.run(
            ["systemctl", "show", unit, f"--property={prop}", "--value"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def unit_enabled(self, unit: str) -> bool:
        return (
            subprocess.run(["systemctl", "is-enabled", "--quiet", unit], check=False).returncode
            == 0
        )

    def unit_active(self, unit: str) -> bool:
        return (
            subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
        )

    def unit_main_pid(self, unit: str) -> int:
        raw_pid = self._show(unit, "MainPID")
        return int(raw_pid) if raw_pid.isdigit() else 0

    def daemon_reload(self) -> None:
        subprocess.run(["systemctl", "daemon-reload"], check=True)

    def enable_unit(self, unit: str) -> None:
        subprocess.run(["systemctl", "enable", unit], check=True)

    def disable_unit(self, unit: str) -> None:
        subprocess.run(["systemctl", "disable", unit], check=True)

    def start_unit(self, unit: str) -> None:
        subprocess.run(["systemctl", "start", unit], check=True)

    def stop_unit(self, unit: str) -> None:
        subprocess.run(["systemctl", "stop", unit], check=True)

    def restart_unit(self, unit: str) -> None:
        subprocess.run(["systemctl", "restart", unit], check=True)


@dataclass(frozen=True)
class InstallPreview:
    manifest_digest: str
    accounts: tuple[str, ...]
    directories: tuple[str, ...]
    files: tuple[str, ...]
    path_units: tuple[str, ...]
    mutates_system: Literal[False] = False


class PrivilegedInstaller:
    """Apply, replay, attest, or roll back one exact pinned distribution."""

    def __init__(
        self,
        bundle_root: Path,
        spec: PrivilegedInstallSpec,
        *,
        root: Path = Path("/"),
        authority: AuthorityBackend | None = None,
        system: SystemBackend | None = None,
        fail_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.bundle_root = bundle_root
        self.spec = spec
        self.root = root
        self.authority = authority or LinuxAuthority()
        self.system = system or LinuxSystemd()
        self.fail_hook = fail_hook
        self._state: dict[str, object] = {}
        key = spec.manifest_digest.removeprefix("sha256:")
        self.txn = self._target(f"/var/lib/traincapsule-verifier-installer/{key}")

    @classmethod
    def load(
        cls,
        bundle_root: Path,
        **kwargs: object,
    ) -> PrivilegedInstaller:
        manifest = bundle_root / "installer-manifest.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise InstallFailure("installer manifest must be a regular file")
        try:
            spec = PrivilegedInstallSpec.model_validate_json(manifest.read_bytes())
        except (ValueError, OSError) as exc:
            raise InstallFailure("installer manifest is invalid") from exc
        return cls(bundle_root, spec, **kwargs)  # pyright: ignore[reportArgumentType]

    def preview(self) -> InstallPreview:
        self._preflight_sources(require_privileged_bundle=False)
        return InstallPreview(
            manifest_digest=self.spec.manifest_digest,
            accounts=(
                self.spec.service_account.name,
                self.spec.selector_account.name,
                self.spec.ruleset_account.name,
                self.spec.token_refresher_account.name,
                self.spec.anchor_fetcher_account.name,
                self.spec.controller_account.name,
            ),
            directories=tuple(item.target for item in self.spec.directories),
            files=tuple(item.target for item in self.spec.files),
            path_units=tuple(self.spec.path_units),
        )

    def apply(self, confirmation: str | None = None) -> DeploymentAttestation | InstallPreview:
        if confirmation is None:
            return self.preview()
        if confirmation != APPLY_CONFIRMATION:
            raise InstallFailure("explicit privileged-install confirmation token is required")
        simulated = self.authority.simulated and self.system.simulated
        if not simulated and (self.root != Path("/") or os.geteuid() != 0):
            raise InstallFailure("production apply requires uid 0 and the real filesystem root")
        if not simulated and not self.system.system_ready():
            raise InstallFailure(
                "production apply requires a booted and reachable systemd manager"
            )
        self._preflight_sources(require_privileged_bundle=not simulated)
        self._require_stopped_controller()
        self._open_transaction()
        if self._state.get("status") == "COMMITTED":
            return self.attest(require_paths=True)
        try:
            self._ensure_accounts()
            self._ensure_directories()
            self._ensure_stop_marker()
            self._stage_sources()
            self._install_runtime_distribution()
            self._install_files()
            self._install_repository_snapshot()
            self._attest_installed_tree()
            self._reload_and_leave_controller_stopped()
            attestation = self.attest(require_paths=False)
            self._enable_paths_after_attestation()
            attestation = self.attest(require_paths=True)
            self._state["status"] = "COMMITTED"
            self._save_state()
            self._record("COMMIT", {"state": attestation.state})
            return attestation
        except Exception:
            self.rollback()
            raise

    def attest(self, *, require_paths: bool) -> DeploymentAttestation:
        if not self._state:
            self._load_state()
        negative = self._attest_installed_tree()
        if self._state.get("daemonReloadComplete") is not True:
            raise InstallFailure("installed systemd graph has not been reloaded")
        principal = self.spec.controller_account.name
        if self.system.unit_active(self.spec.controller_unit) or self.system.unit_enabled(
            self.spec.controller_unit
        ):
            raise InstallFailure("controller service is not disabled and inactive")
        enabled = all(
            self.system.unit_enabled(unit) and self.system.unit_active(unit)
            for unit in self.spec.path_units
        )
        if require_paths and not enabled:
            raise InstallFailure("one or more verifier path units are not enabled and active")
        return DeploymentAttestation(
            state="PATH_UNITS_ENABLED" if enabled else "FILES_ATTESTED",
            manifest_digest=self.spec.manifest_digest,
            controller_principal=principal,
            checked_directories=len(self.spec.directories),
            checked_files=len(self.spec.files),
            negative_access_checks=negative,
            path_units_enabled=enabled,
        )

    def _attest_installed_tree(self) -> int:
        for item in self.spec.directories:
            target = self._target(item.target)
            self._attest_metadata(target, item.owner, item.group, item.mode, directory=True)
        for item in self.spec.files:
            target = self._target(item.target)
            self._attest_metadata(target, item.owner, item.group, item.mode, directory=False)
            if _sha256_file(target) != item.sha256:
                raise InstallFailure(f"installed digest mismatch: {item.target}")
        self._attest_runtime_distribution()
        self._attest_repository_snapshot()
        self._attest_controller_runtime_contract()
        self._attest_activation_supervisor_unit()
        return self._attest_access_boundary()

    def rollback(self) -> None:
        self._load_state()
        if (
            not self._state
            or self._state.get("initialized") is not True
            or self._state.get("manifest") != self.spec.manifest_digest
            or self._state.get("status") == "ROLLED_BACK"
        ):
            return
        system_effects = self._state.get("systemEffectsStarted") is True
        units = cast(dict[str, dict[str, object]], self._state.get("units", {}))
        if system_effects:
            for unit in reversed(self._managed_units()):
                baseline = units[unit]
                if not bool(baseline["active"]) and self.system.unit_active(unit):
                    self._unit_transition("ROLLBACK_STOP", unit, self.system.stop_unit)
        resources = cast(dict[str, dict[str, object]], self._state.get("resources", {}))
        snapshot_entries = cast(
            dict[str, dict[str, object]], self._state.get("snapshotEntries", {})
        )
        snapshot_root = self._target("/var/lib/traincapsule-verifier/repository-boundary")
        if snapshot_root.is_dir():
            os.chmod(snapshot_root, 0o700, follow_symlinks=False)
        for relative in sorted(snapshot_entries, key=lambda value: value.count("/")):
            target = snapshot_root / relative
            if target.is_dir() and not target.is_symlink():
                os.chmod(target, 0o700, follow_symlinks=False)
        for relative in sorted(
            snapshot_entries,
            key=lambda value: (value.count("/"), value),
            reverse=True,
        ):
            target = snapshot_root / relative
            if target.is_symlink():
                raise InstallFailure("rollback snapshot entry changed type")
            if target.is_file():
                target.unlink()
            elif target.is_dir() and not any(target.iterdir()):
                target.rmdir()
            self._record("SNAPSHOT_ENTRY_ROLLED_BACK", {"path": relative})
        files = {item.target for item in self.spec.files}
        files.add("/var/lib/traincapsule-runtime/STOP")
        for target_text in reversed([item.target for item in self.spec.files]):
            saved = resources.get(target_text)
            if saved is None:
                continue
            target = self._target(target_text)
            if bool(saved["existed"]):
                backup = self.txn / cast(str, saved["backup"])
                if not backup.is_file():
                    raise InstallFailure(f"rollback backup is missing for {target_text}")
                _atomic_replace(target, backup.read_bytes(), int(cast(str, saved["mode"]), 8))
                os.chmod(target, int(cast(str, saved["mode"]), 8), follow_symlinks=False)
                uid = cast(int, saved["uid"])
                gid = cast(int, saved["gid"])
                self.authority.restore_owner(target, uid, gid)
            elif target.exists() and target_text in files:
                if target.is_symlink() or not target.is_file():
                    raise InstallFailure(f"rollback target changed type: {target_text}")
                target.unlink()
            self._record("FILE_ROLLED_BACK", {"target": target_text})
        runtime_root = self._target("/opt/traincapsule-runtime/python")
        runtime_entries = cast(list[str], self._state.get("runtimeEntries", []))
        if runtime_entries and runtime_root.is_dir() and not runtime_root.is_symlink():
            os.chmod(runtime_root, 0o700, follow_symlinks=False)
            for directory in sorted(
                (path for path in runtime_root.rglob("*") if path.is_dir()),
                reverse=True,
            ):
                if directory.is_symlink():
                    raise InstallFailure("rollback runtime directory changed type")
                os.chmod(directory, 0o700, follow_symlinks=False)
            for relative in sorted(
                runtime_entries,
                key=lambda value: (value.count("/"), value),
                reverse=True,
            ):
                target = runtime_root / relative
                if target.is_symlink():
                    raise InstallFailure("rollback runtime entry changed type")
                if target.is_file():
                    target.unlink()
                parent = target.parent
                while parent != runtime_root and parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            if not any(runtime_root.iterdir()):
                runtime_root.rmdir()
            self._record("RUNTIME_DISTRIBUTION_ROLLED_BACK", {})
        for item in reversed(self.spec.directories):
            saved = resources.get(item.target)
            if saved is None:
                continue
            target = self._target(item.target)
            if bool(saved["existed"]) and target.is_dir():
                os.chmod(target, int(cast(str, saved["mode"]), 8), follow_symlinks=False)
                self.authority.restore_owner(
                    target, cast(int, saved["uid"]), cast(int, saved["gid"])
                )
            elif target.is_dir() and target != self.txn and not any(target.iterdir()):
                target.rmdir()
            self._record("DIRECTORY_ROLLED_BACK", {"target": item.target})
        if system_effects:
            self.system.daemon_reload()
            self._record("ROLLBACK_DAEMON_RELOADED", {})
            for unit in self._managed_units():
                baseline = units[unit]
                wanted_enabled = bool(baseline["enabled"])
                if self.system.unit_enabled(unit) != wanted_enabled:
                    action = self.system.enable_unit if wanted_enabled else self.system.disable_unit
                    self._unit_transition("ROLLBACK_ENABLE_STATE", unit, action)
                wanted_active = bool(baseline["active"])
                if wanted_active:
                    action = (
                        self.system.restart_unit
                        if self.system.unit_active(unit)
                        else self.system.start_unit
                    )
                    self._unit_transition("ROLLBACK_ACTIVE_STATE", unit, action)
                elif self.system.unit_active(unit):
                    self._unit_transition("ROLLBACK_ACTIVE_STATE", unit, self.system.stop_unit)
        self._record("ROLLBACK_COMPLETE", {})
        if self._state:
            self._state["status"] = "ROLLED_BACK"
            self._save_state()

    def _preflight_sources(self, *, require_privileged_bundle: bool) -> None:
        bundle = self.bundle_root.resolve(strict=True)
        if self.bundle_root.is_symlink() or not bundle.is_dir():
            raise InstallFailure("bundle root must be a real directory")
        if require_privileged_bundle:
            info = bundle.stat()
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise InstallFailure(
                    "production bundle must be root-owned and not group/world writable"
                )
            protected = [self.bundle_root / "installer-manifest.json"]
            protected.extend(self._source(item.source) for item in self.spec.files)
            for path in protected:
                current = path
                while True:
                    path_info = current.stat()
                    if path_info.st_uid != 0 or stat.S_IMODE(path_info.st_mode) & 0o022:
                        raise InstallFailure(
                            "production bundle member or parent is not privileged read-only: "
                            f"{path.name}"
                        )
                    if current == bundle:
                        break
                    current = current.parent
        for item in self.spec.files:
            source = self._source(item.source)
            if _sha256_file(source) != item.sha256:
                raise InstallFailure(f"source digest mismatch: {item.source}")
        by_role = {item.role: item for item in self.spec.files}
        snapshot_manifest = load_repository_snapshot_manifest(
            self._source(by_role["repository-snapshot-manifest"].source)
        )
        validate_repository_snapshot_archive(
            self._source(by_role["repository-snapshot"].source), snapshot_manifest
        )
        runtime_distribution = RuntimeDistributionManifest.model_validate_json(
            self._source(by_role["python-runtime-distribution-manifest"].source).read_bytes(),
            strict=True,
        )
        validate_runtime_distribution(
            self._source(by_role["python-runtime-archive"].source), runtime_distribution
        )
        if (
            runtime_distribution.executable_digest != by_role["python-runtime"].sha256
            or runtime_distribution.archive_digest != by_role["python-runtime-archive"].sha256
        ):
            raise InstallFailure("runtime distribution deployment binding mismatch")
        bindings = {
            "effectiveConfigDigest": by_role["controller-effective-config"].sha256,
            "pythonRuntimeManifestDigest": by_role["python-runtime-manifest"].sha256,
            "packageManifestDigest": by_role["controller-package-manifest"].sha256,
            "dependencyLockDigest": by_role["controller-dependency-lock"].sha256,
        }
        snapshot_payload = snapshot_manifest.model_dump(mode="json", by_alias=True)
        if any(snapshot_payload[field] != digest for field, digest in bindings.items()):
            raise InstallFailure("repository snapshot deployment binding mismatch")
        try:
            producer_raw = self._source(by_role["git-anchor-producer-policy"].source).read_bytes()
            updater_raw = self._source(by_role["git-anchor-policy"].source).read_bytes()
            producer_value: object = json.loads(producer_raw)
            updater_value: object = json.loads(updater_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InstallFailure("Git anchor policy is invalid") from exc
        if not isinstance(producer_value, dict) or not isinstance(updater_value, dict):
            raise InstallFailure("Git anchor policy is invalid")
        producer_policy = cast(dict[str, object], producer_value)
        updater_policy = cast(dict[str, object], updater_value)
        app_id = producer_policy.get("githubAppId")
        installation_id = producer_policy.get("installationId")
        if (
            canonical_json_bytes(producer_policy) != producer_raw
            or type(app_id) is not int
            or app_id <= 0
            or type(installation_id) is not int
            or installation_id <= 0
            or producer_policy.get("sourceGenerationId")
            != updater_policy.get("sourceGenerationId")
            or producer_policy.get("sourceGenerationDigest")
            != updater_policy.get("sourceGenerationDigest")
            or producer_policy.get("sourceGenerationDigest")
            != snapshot_manifest.source_generation_digest
        ):
            raise InstallFailure("Git anchor producer policy is not deployment-bound")
        unit_digests = {
            item.path: item.content_digest for item in production_install_manifest().files
        }
        for item in self.spec.files:
            if (
                item.target in unit_digests
                and item.role not in {"git-anchor-policy", "git-anchor-producer-policy"}
                and unit_digests[item.target] != item.sha256
            ):
                raise InstallFailure(f"systemd unit is not the repository-pinned unit: {item.role}")
        targets = [item.target for item in self.spec.directories] + [
            item.target for item in self.spec.files
        ]
        if len(targets) != len(set(targets)):
            raise InstallFailure("duplicate install target")

    def _open_transaction(self) -> None:
        journal_root = self.txn.parent
        _reject_symlink_parents(journal_root, self.root)
        journal_root.mkdir(mode=0o700, exist_ok=True)
        for directory in (journal_root, self.txn):
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise InstallFailure(f"transaction journal path is unsafe: {directory}")
            self.authority.chown(directory, "root", "root")
            os.chmod(directory, 0o700, follow_symlinks=False)
        for name in ("backup", "stage"):
            directory = self.txn / name
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise InstallFailure(f"transaction journal child is unsafe: {directory}")
            self.authority.chown(directory, "root", "root")
            os.chmod(directory, 0o700, follow_symlinks=False)
        self._load_state()
        if not self._state:
            self._state = {
                "manifest": self.spec.manifest_digest,
                "initialized": False,
                "resources": {},
                "snapshotEntries": {},
                "accounts": {},
            }
            self._save_state()
            self._record("BEGIN", {})
        elif self._state.get("manifest") != self.spec.manifest_digest:
            raise InstallFailure("transaction journal belongs to another manifest")
        elif self._state.get("status") == "ROLLED_BACK":
            self._state = {
                "manifest": self.spec.manifest_digest,
                "initialized": False,
                "resources": {},
                "snapshotEntries": {},
                "accounts": {},
            }
            self._save_state()
            self._record("BEGIN_RETRY", {})
        if self._state.get("initialized") is not True:
            if self._state.get("resources") or self._state.get("accounts"):
                raise InstallFailure("incomplete legacy journal cannot be replayed safely")
            units: dict[str, dict[str, object]] = {}
            for unit in self._managed_units():
                units[unit] = {
                    "enabled": self.system.unit_enabled(unit),
                    "active": self.system.unit_active(unit),
                    "mainPid": (
                        self.system.unit_main_pid(unit) if unit == self.spec.controller_unit else 0
                    ),
                }
            self._state["units"] = units
            self._state["initialized"] = True
            self._save_state()
            self._record("UNIT_BASELINES_CAPTURED", {"units": units})

    def _ensure_accounts(self) -> None:
        accounts = cast(dict[str, object], self._state["accounts"])
        for account in (
            self.spec.service_account,
            self.spec.selector_account,
            self.spec.ruleset_account,
            self.spec.token_refresher_account,
            self.spec.anchor_fetcher_account,
            self.spec.controller_account,
        ):
            if account.name in accounts:
                self.authority.ensure_locked(account)
                continue
            created = self.authority.ensure_locked(account)
            accounts[account.name] = {"created": created, "retainedOnRollback": True}
            self._save_state()
            self._record("ACCOUNT_ATTESTED", {"name": account.name, "created": created})
            self._fail("account:" + account.name)

    def _ensure_directories(self) -> None:
        for item in self.spec.directories:
            target = self._target(item.target)
            saved = self._prepare_resource(item.target, target, directory=True)
            target.mkdir(parents=False, exist_ok=True)
            if target.is_symlink() or not target.is_dir():
                raise InstallFailure(f"directory target is unsafe: {item.target}")
            self.authority.chown(target, item.owner, item.group)
            os.chmod(target, int(item.mode, 8), follow_symlinks=False)
            saved["complete"] = True
            self._save_state()
            self._record("DIRECTORY_INSTALLED", {"target": item.target})
            self._fail("directory:" + item.target)

    def _ensure_stop_marker(self) -> None:
        target_text = "/var/lib/traincapsule-runtime/STOP"
        target = self._target(target_text)
        saved = self._prepare_resource(target_text, target, directory=False)
        if not bool(saved["existed"]):
            _atomic_replace(target, b"stopped pending independent activation\n", 0o600)
            self.authority.chown(
                target,
                self.spec.controller_account.name,
                self.spec.controller_account.name,
            )
        self._attest_metadata(
            target,
            self.spec.controller_account.name,
            self.spec.controller_account.name,
            "0600",
            directory=False,
        )
        saved["complete"] = True
        self._save_state()
        self._record("STOP_CONTROL_ATTESTED", {"target": target_text})
        self._fail("control:STOP")

    def _stage_sources(self) -> None:
        stage = self.txn / "stage"
        for item in self.spec.files:
            staged = stage / item.role
            if staged.exists():
                if _sha256_file(staged) != item.sha256:
                    raise InstallFailure(f"transaction stage conflict: {item.role}")
                continue
            data = self._source(item.source).read_bytes()
            if sha256_digest(data) != item.sha256:
                raise InstallFailure(f"source changed during staging: {item.source}")
            _atomic_replace(staged, data, 0o600)
            self._record("SOURCE_STAGED", {"role": item.role, "digest": item.sha256})
            self._fail("stage:" + item.role)

    def _install_files(self) -> None:
        for item in self.spec.files:
            if item.role in {"python-runtime", "repository-snapshot-manifest"}:
                continue
            target = self._target(item.target)
            saved = self._prepare_resource(item.target, target, directory=False)
            staged = self.txn / "stage" / item.role
            _atomic_replace(target, staged.read_bytes(), int(item.mode, 8))
            self.authority.chown(target, item.owner, item.group)
            os.chmod(target, int(item.mode, 8), follow_symlinks=False)
            saved["complete"] = True
            self._save_state()
            self._record("FILE_INSTALLED", {"target": item.target, "digest": item.sha256})
            self._fail("file:" + item.role)

    def _install_runtime_distribution(self) -> None:
        by_role = {item.role: item for item in self.spec.files}
        destination = self._target("/opt/traincapsule-runtime/python")
        archive = self.txn / "stage" / "python-runtime-archive"
        manifest_raw = (self.txn / "stage" / "python-runtime-distribution-manifest").read_bytes()
        manifest = RuntimeDistributionManifest.model_validate_json(manifest_raw, strict=True)
        entries = [entry.path for entry in manifest.entries]
        if destination.exists() or destination.is_symlink():
            if (
                self._state.get("runtimeEntries") != entries
                or self._state.get("runtimeManifestDigest") != manifest.manifest_digest
            ):
                raise InstallFailure("runtime distribution destination already exists")
            validate_extracted_runtime_distribution(destination, manifest)
        else:
            extract_runtime_distribution(archive, manifest, destination)
            self._state["runtimeEntries"] = entries
            self._state["runtimeManifestDigest"] = manifest.manifest_digest
            self._save_state()
        for path in [destination, *destination.rglob("*")]:
            self.authority.chown(path, "root", "root")
        executable = destination / manifest.executable_path
        if _sha256_file(executable) != by_role["python-runtime"].sha256:
            raise InstallFailure("installed runtime executable differs")
        self._record(
            "RUNTIME_DISTRIBUTION_INSTALLED",
            {"manifest": manifest.manifest_digest, "entries": len(entries)},
        )
        self._fail("runtime-distribution")

    def _attest_runtime_distribution(self) -> None:
        by_role = {item.role: item for item in self.spec.files}
        manifest_path = self._target(
            by_role["python-runtime-distribution-manifest"].target
        )
        manifest = RuntimeDistributionManifest.model_validate_json(
            manifest_path.read_bytes(), strict=True
        )
        destination = self._target("/opt/traincapsule-runtime/python")
        validate_extracted_runtime_distribution(destination, manifest)
        expected_owner = (
            self.authority.uid("root"),
            self.authority.gid("root"),
        )
        for path in [destination, *destination.rglob("*")]:
            if self.authority.owner(path) != expected_owner:
                raise InstallFailure("runtime distribution owner differs")

    def _install_repository_snapshot(self) -> None:
        by_role = {item.role: item for item in self.spec.files}
        manifest = load_repository_snapshot_manifest(
            self.txn / "stage" / "repository-snapshot-manifest"
        )
        archive_path = self._target(by_role["repository-snapshot"].target)
        validate_repository_snapshot_archive(archive_path, manifest)
        snapshot_root = self._target("/var/lib/traincapsule-verifier/repository-boundary")
        recorded = cast(dict[str, dict[str, object]], self._state["snapshotEntries"])
        allowed_existing = {
            self._target(by_role["repository-snapshot-manifest"].target).name,
            *recorded,
        }
        unexpected = {
            path.name for path in snapshot_root.iterdir() if path.name not in allowed_existing
        }
        if unexpected:
            raise InstallFailure("repository snapshot target is not empty or replay-owned")
        os.chmod(snapshot_root, 0o700, follow_symlinks=False)
        manifest_target = self._target(by_role["repository-snapshot-manifest"].target)
        manifest_state = self._prepare_resource(
            by_role["repository-snapshot-manifest"].target,
            manifest_target,
            directory=False,
        )
        staged_manifest = self.txn / "stage" / "repository-snapshot-manifest"
        _atomic_replace(manifest_target, staged_manifest.read_bytes(), 0o444)
        self.authority.chown(manifest_target, "root", "root")
        manifest_state["complete"] = True
        self._save_state()
        self._record(
            "FILE_INSTALLED",
            {
                "target": by_role["repository-snapshot-manifest"].target,
                "digest": by_role["repository-snapshot-manifest"].sha256,
            },
        )
        directories: list[tuple[Path, int]] = []
        try:
            with zipfile.ZipFile(archive_path) as archive:
                info_by_name = {
                    info.filename.removesuffix("/"): info for info in archive.infolist()
                }
                for entry in manifest.entries:
                    target = snapshot_root.joinpath(*PurePosixPath(entry.path).parts)
                    existing_state = recorded.get(entry.path)
                    if existing_state is None:
                        if target.exists() or target.is_symlink():
                            raise InstallFailure("snapshot entry collides with preexisting data")
                        state: dict[str, object] = {
                            "complete": False,
                            "kind": entry.kind,
                        }
                        recorded[entry.path] = state
                        self._save_state()
                        self._record("SNAPSHOT_ENTRY_PREPARED", {"path": entry.path})
                    else:
                        state = existing_state
                    if entry.kind == "directory":
                        target.mkdir(mode=0o700, exist_ok=True)
                        if target.is_symlink() or not target.is_dir():
                            raise InstallFailure("snapshot directory replay changed type")
                        directories.append((target, int(entry.mode, 8)))
                    else:
                        if target.exists():
                            if target.is_symlink() or not target.is_file():
                                raise InstallFailure("snapshot file replay changed type")
                            if _sha256_file(target) != entry.digest:
                                raise InstallFailure("snapshot file replay digest mismatch")
                        else:
                            _atomic_replace(
                                target,
                                archive.read(info_by_name[entry.path]),
                                int(entry.mode, 8),
                            )
                        self.authority.chown(target, "root", "root")
                        os.chmod(target, int(entry.mode, 8), follow_symlinks=False)
                    state["complete"] = True
                    self._save_state()
                    self._record("SNAPSHOT_ENTRY_INSTALLED", {"path": entry.path})
                    self._fail("snapshot:" + entry.path)
            for directory, mode in reversed(directories):
                self.authority.chown(directory, "root", "root")
                os.chmod(directory, mode, follow_symlinks=False)
        finally:
            self.authority.chown(snapshot_root, "root", "root")
            os.chmod(snapshot_root, 0o555, follow_symlinks=False)

    def _prepare_resource(self, key: str, target: Path, *, directory: bool) -> dict[str, object]:
        resources = cast(dict[str, dict[str, object]], self._state["resources"])
        if key in resources:
            return resources[key]
        _reject_symlink_parents(target, self.root)
        existed = target.exists()
        saved: dict[str, object] = {"existed": existed, "directory": directory, "complete": False}
        if existed:
            if target.is_symlink() or (directory != target.is_dir()):
                raise InstallFailure(f"existing target has the wrong type: {key}")
            info = target.lstat()
            uid, gid = self.authority.owner(target)
            saved.update({"uid": uid, "gid": gid, "mode": f"0{stat.S_IMODE(info.st_mode):03o}"})
            if not directory:
                backup_name = "backup/" + hashlib.sha256(key.encode()).hexdigest()
                backup = self.txn / backup_name
                if not backup.exists():
                    _atomic_replace(backup, target.read_bytes(), 0o600)
                saved["backup"] = backup_name
        resources[key] = saved
        self._save_state()
        self._record("RESOURCE_PREPARED", {"target": key, "existed": existed})
        return saved

    def _managed_units(self) -> tuple[str, ...]:
        values = {
            PurePosixPath(item.target).name
            for item in self.spec.files
            if item.target.startswith("/etc/systemd/system/")
        }
        return tuple(sorted(values))

    def _unit_transition(self, event: str, unit: str, action: Callable[[str], None]) -> None:
        self._record(event + "_ATTEMPT", {"unit": unit})
        try:
            action(unit)
        except Exception as exc:
            self._record(event + "_FAILED", {"unit": unit, "errorType": type(exc).__name__})
            raise
        self._record(event + "_COMPLETE", {"unit": unit})

    def _require_stopped_controller(self) -> None:
        if self.system.unit_active(self.spec.controller_unit):
            raise InstallFailure(
                "an active controller cannot be adopted by the receipt-gated installation"
            )

    def _reload_and_leave_controller_stopped(self) -> None:
        self._state["systemEffectsStarted"] = True
        self._save_state()
        self._record("SYSTEM_EFFECTS_BEGIN", {})
        self.system.daemon_reload()
        self._record("DAEMON_RELOADED_AFTER_ATTESTATION", {})
        self._state["daemonReloadComplete"] = True
        self._save_state()
        unit = self.spec.controller_unit
        if self.system.unit_active(unit):
            raise InstallFailure("controller became active before receipt-gated broker approval")
        if self.system.unit_enabled(unit):
            self._unit_transition("CONTROLLER_DISABLE", unit, self.system.disable_unit)

    def _enable_paths_after_attestation(self) -> None:
        authority_service = "traincapsule-external-evidence-authority.service"
        self._unit_transition(
            "AUTHORITY_BOOTSTRAP",
            authority_service,
            self.system.start_unit,
        )
        if self.system.unit_active(authority_service):
            self._unit_transition(
                "AUTHORITY_BOOTSTRAP_STOP",
                authority_service,
                self.system.stop_unit,
            )
        for unit in self.spec.path_units:
            if not self.system.unit_enabled(unit):
                self._unit_transition("PATH_ENABLE", unit, self.system.enable_unit)
            if self.system.unit_active(unit):
                self._unit_transition("PATH_RESTART", unit, self.system.restart_unit)
            else:
                self._unit_transition("PATH_START", unit, self.system.start_unit)
            self._fail("enable:" + unit)

    def _attest_metadata(
        self, target: Path, owner: str, group: str, mode: str, *, directory: bool
    ) -> None:
        _reject_symlink_parents(target, self.root)
        if target.is_symlink() or not target.exists() or target.is_dir() != directory:
            raise InstallFailure(f"installed object is missing or unsafe: {target}")
        uid, gid = self.authority.owner(target)
        if (uid, gid) != (self.authority.uid(owner), self.authority.gid(group)):
            raise InstallFailure(f"installed owner mismatch: {target}")
        metadata = target.lstat()
        if not directory and metadata.st_nlink != 1:
            raise InstallFailure(f"installed file has an unsafe link count: {target}")
        actual_mode = stat.S_IMODE(metadata.st_mode)
        if actual_mode != int(mode, 8):
            raise InstallFailure(f"installed mode mismatch: {target}")

    def _attest_controller_runtime_contract(self) -> None:
        unit_path = self._target(ROLE_TARGETS["controller-service"])
        unit = unit_path.read_text(encoding="utf-8")
        principal = self.spec.controller_account.name
        arguments = (
            "-m tcfactory.cli v3-controller --repo "
            "/var/lib/traincapsule-verifier/repository-boundary"
        )
        required = (
            "[Service]",
            f"User={principal}",
            f"Group={principal}",
            f"ExecStart={ROLE_TARGETS['python-runtime']} {arguments}",
            f"EnvironmentFile={ROLE_TARGETS['controller-runtime-environment']}",
            "WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary",
            "NoNewPrivileges=yes",
        )
        lines = unit.splitlines()
        if (
            any(line not in lines for line in required)
            or sum(line.startswith("ExecStart=") for line in lines) != 1
            or sum(line.startswith("User=") for line in lines) != 1
            or sum(line.startswith("Group=") for line in lines) != 1
        ):
            raise InstallFailure("controller unit does not bind the exact installed runtime")

        manifest_path = self._target(ROLE_TARGETS["installed-controller-runtime-manifest"])
        raw = manifest_path.read_bytes()
        try:
            parsed: object = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InstallFailure("installed controller runtime manifest is invalid") from exc
        if not isinstance(parsed, dict):
            raise InstallFailure("installed controller runtime manifest is invalid")
        manifest = cast(dict[str, object], parsed)
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
            "reductionOracle",
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
            or manifest["controllerPrincipal"] != principal
            or manifest["serviceName"] != self.spec.controller_unit
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
                "tcfactory.cli",
                "v3-controller",
                "--repo",
                "/var/lib/traincapsule-verifier/repository-boundary",
            ]
            or canonical_json_bytes(manifest) != raw
        ):
            raise InstallFailure("installed controller runtime contract is not exact")
        zeroed = dict(manifest)
        zeroed["manifestDigest"] = "sha256:" + "0" * 64
        if manifest["manifestDigest"] != sha256_digest(canonical_json_bytes(zeroed)):
            raise InstallFailure("installed controller runtime manifest digest mismatch")
        artifact_roles = {
            "pythonRuntime": ("python-runtime", True),
            "packageManifest": ("controller-package-manifest", False),
            "dependencyLock": ("controller-dependency-lock", False),
            "controllerUnit": ("controller-service", False),
            "environmentFile": ("controller-runtime-environment", False),
            "effectiveConfig": ("controller-effective-config", False),
            "repositorySnapshotManifest": ("repository-snapshot-manifest", False),
        }
        pins = {item.role: item for item in self.spec.files}
        for field, (role, executable) in artifact_roles.items():
            artifact = manifest[field]
            pin = pins[role]
            if not isinstance(artifact, dict) or artifact != {
                "path": pin.target,
                "digest": pin.sha256,
                "executable": executable,
            }:
                raise InstallFailure("installed controller runtime artifact pin mismatch")
        reduction_oracle = manifest["reductionOracle"]
        expected_reduction_oracle = {
            "oracleId": "TRAINCAPSULE_REDUCTION_ORACLE_V1",
            "executable": {
                "path": pins["reduction-oracle"].target,
                "digest": pins["reduction-oracle"].sha256,
                "executable": True,
            },
            "publicKey": {
                "path": pins["reduction-oracle-public-key"].target,
                "digest": pins["reduction-oracle-public-key"].sha256,
                "executable": False,
            },
            "receiptVerifier": {
                "path": pins["public-verifier"].target,
                "digest": pins["public-verifier"].sha256,
                "executable": True,
            },
            "publicReceiptRoot": "/var/lib/traincapsule-verifier/receipts",
            "activationReceiptPath": (
                "/var/lib/traincapsule-verifier/activation/current.json"
            ),
        }
        if reduction_oracle != expected_reduction_oracle:
            raise InstallFailure("installed reduction oracle pin mismatch")
        snapshot = load_repository_snapshot_manifest(
            self._target(ROLE_TARGETS["repository-snapshot-manifest"])
        )
        if (
            manifest["repositoryMainSha"] != snapshot.main_sha
            or manifest["repositoryTreeSha"] != snapshot.tree_sha
        ):
            raise InstallFailure("controller runtime repository identity mismatch")

    def _attest_repository_snapshot(self) -> None:
        manifest = load_repository_snapshot_manifest(
            self._target(ROLE_TARGETS["repository-snapshot-manifest"])
        )
        root = self._target("/var/lib/traincapsule-verifier/repository-boundary")
        expected = {entry.path: entry for entry in manifest.entries}
        observed_paths = {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.relative_to(root) != Path("SNAPSHOT_MANIFEST.json")
        }
        if observed_paths != set(expected):
            raise InstallFailure("installed repository snapshot inventory mismatch")
        for relative, entry in expected.items():
            target = root.joinpath(*PurePosixPath(relative).parts)
            self._attest_metadata(
                target,
                "root",
                "root",
                entry.mode,
                directory=entry.kind == "directory",
            )
            if entry.digest is not None and _sha256_file(target) != entry.digest:
                raise InstallFailure("installed repository snapshot digest mismatch")
        git = root / ".git"
        if (git / "objects/info/alternates").exists() or (git / "hooks").exists():
            raise InstallFailure("installed repository has external Git behavior")
        commands = (
            (("fsck", "--strict", "--no-dangling"), None),
            (("remote",), ""),
            (("rev-parse", "HEAD"), manifest.main_sha),
            (("rev-parse", "HEAD^{tree}"), manifest.tree_sha),
            (("status", "--porcelain=v1", "--untracked-files=all"), ""),
        )
        for arguments, expected_output in commands:
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
                    "GIT_OPTIONAL_LOCKS": "0",
                },
            )
            if result.returncode != 0 or (
                expected_output is not None and result.stdout.strip() != expected_output
            ):
                raise InstallFailure("installed repository Git attestation failed")

    def _attest_activation_supervisor_unit(self) -> None:
        unit = self._target(ROLE_TARGETS["activation-supervisor-service"]).read_text(
            encoding="utf-8"
        )
        principal = self.spec.controller_account.name
        required = (
            "[Service]",
            f"User={principal}",
            f"Group={principal}",
            f"ExecStart={ROLE_TARGETS['activation-supervisor-launcher']}",
            "NoNewPrivileges=yes",
        )
        if any(line not in unit.splitlines() for line in required):
            raise InstallFailure(
                "activation supervisor unit does not bind the dedicated controller principal"
            )

    def _attest_access_boundary(self) -> int:
        controller = self.spec.controller_account.name
        service = self.spec.service_account.name
        selector = self.spec.selector_account.name
        ruleset = self.spec.ruleset_account.name
        refresher = self.spec.token_refresher_account.name
        fetcher = self.spec.anchor_fetcher_account.name
        checks: tuple[tuple[str, str, str, bool], ...] = (
            (controller, ROLE_TARGETS["private-key"], "read", False),
            (controller, ROLE_TARGETS["github-app-private-key"], "read", False),
            (controller, ROLE_TARGETS["selector-private-key"], "read", False),
            (controller, ROLE_TARGETS["selector-credential"], "read", False),
            (controller, ROLE_TARGETS["ruleset-private-key"], "read", False),
            (controller, ROLE_TARGETS["ruleset-credential"], "read", False),
            (controller, ROLE_TARGETS["issuer"], "execute", False),
            (controller, ROLE_TARGETS["activation-issuer"], "execute", False),
            (controller, ROLE_TARGETS["check-worker"], "execute", False),
            (controller, ROLE_TARGETS["observed-main-selector"], "execute", False),
            (controller, ROLE_TARGETS["activation-selector-broker"], "execute", False),
            (controller, ROLE_TARGETS["activation-request-broker"], "execute", False),
            (controller, ROLE_TARGETS["controller-start-broker"], "execute", False),
            (controller, ROLE_TARGETS["post-activation-observer"], "execute", False),
            (controller, ROLE_TARGETS["github-token-refresher-private-key"], "read", False),
            (controller, ROLE_TARGETS["github-token-refresher"], "execute", False),
            (controller, ROLE_TARGETS["ruleset-observer"], "execute", False),
            (controller, ROLE_TARGETS["ruleset-broker"], "execute", False),
            (controller, ROLE_TARGETS["git-anchor-updater"], "execute", False),
            (controller, ROLE_TARGETS["git-anchor-producer"], "execute", False),
            (controller, ROLE_TARGETS["deployment-refresh"], "execute", False),
            (
                controller,
                "/var/lib/traincapsule-verifier/deployment-refresh-journal",
                "read",
                False,
            ),
            (controller, "/opt/traincapsule-runtime/generations", "write", False),
            (controller, ROLE_TARGETS["git-anchor-github-private-key"], "read", False),
            (controller, "/var/lib/traincapsule-verifier/anchor-updates", "read", False),
            (controller, ROLE_TARGETS["activation-supervisor-launcher"], "execute", True),
            (controller, ROLE_TARGETS["canary-runner"], "execute", True),
            (controller, ROLE_TARGETS["controller-oauth-token"], "read", True),
            (controller, ROLE_TARGETS["canary-claude-token"], "read", True),
            (controller, ROLE_TARGETS["receipt-broker"], "execute", False),
            (controller, ROLE_TARGETS["request-broker"], "execute", False),
            (controller, ROLE_TARGETS["public-verifier"], "execute", True),
            (controller, ROLE_TARGETS["python-runtime"], "execute", True),
            (
                controller,
                ROLE_TARGETS["installed-controller-runtime-manifest"],
                "read",
                True,
            ),
            (controller, ROLE_TARGETS["controller-package-manifest"], "read", True),
            (controller, ROLE_TARGETS["controller-dependency-lock"], "read", True),
            (controller, ROLE_TARGETS["controller-runtime-environment"], "read", True),
            (controller, ROLE_TARGETS["controller-effective-config"], "read", True),
            (controller, "/var/lib/traincapsule-verifier/controller-outbox", "write", True),
            (
                controller,
                "/var/lib/traincapsule-verifier/activation-controller-outbox",
                "write",
                True,
            ),
            (controller, "/var/lib/traincapsule-verifier/controller-start-outbox", "write", True),
            (
                controller,
                "/var/lib/traincapsule-verifier/repository-boundary",
                "read",
                True,
            ),
            (
                controller,
                "/var/lib/traincapsule-verifier/repository-boundary",
                "write",
                False,
            ),
            (controller, "/var/lib/traincapsule-runtime", "write", True),
            (service, ROLE_TARGETS["private-key"], "read", True),
            (service, ROLE_TARGETS["github-app-private-key"], "read", True),
            (service, ROLE_TARGETS["issuer"], "execute", True),
            (service, ROLE_TARGETS["activation-issuer"], "execute", True),
            (service, ROLE_TARGETS["check-worker"], "execute", True),
            (service, ROLE_TARGETS["git-anchor-updater"], "execute", False),
            (service, ROLE_TARGETS["git-anchor-producer"], "execute", False),
            (service, ROLE_TARGETS["selector-private-key"], "read", False),
            (service, ROLE_TARGETS["selector-credential"], "read", False),
            (service, ROLE_TARGETS["ruleset-private-key"], "read", False),
            (service, ROLE_TARGETS["ruleset-credential"], "read", False),
            (service, ROLE_TARGETS["controller-oauth-token"], "read", False),
            (service, ROLE_TARGETS["canary-claude-token"], "read", False),
            (service, "/var/lib/traincapsule-canary-secrets", "read", False),
            (service, "/var/lib/traincapsule-verifier/receipts", "write", False),
            (selector, ROLE_TARGETS["selector-private-key"], "read", True),
            (selector, ROLE_TARGETS["selector-credential"], "read", True),
            (selector, ROLE_TARGETS["private-key"], "read", False),
            (selector, ROLE_TARGETS["github-app-private-key"], "read", False),
            (selector, ROLE_TARGETS["controller-oauth-token"], "read", False),
            (selector, ROLE_TARGETS["canary-claude-token"], "read", False),
            (selector, "/var/lib/traincapsule-canary-secrets", "read", False),
            (selector, ROLE_TARGETS["ruleset-private-key"], "read", False),
            (selector, ROLE_TARGETS["issuer"], "execute", False),
            (selector, ROLE_TARGETS["observed-main-selector"], "execute", True),
            (selector, ROLE_TARGETS["git-anchor-updater"], "execute", False),
            (selector, ROLE_TARGETS["git-anchor-producer"], "execute", False),
            (selector, "/var/lib/traincapsule-verifier/activation-requests", "read", True),
            (selector, "/var/lib/traincapsule-verifier/selector-outbox", "write", True),
            (selector, "/var/lib/traincapsule-verifier/ruleset", "read", True),
            (ruleset, ROLE_TARGETS["ruleset-private-key"], "read", True),
            (ruleset, ROLE_TARGETS["ruleset-credential"], "read", True),
            (ruleset, ROLE_TARGETS["ruleset-observer"], "execute", True),
            (ruleset, ROLE_TARGETS["git-anchor-updater"], "execute", False),
            (ruleset, ROLE_TARGETS["git-anchor-producer"], "execute", False),
            (ruleset, ROLE_TARGETS["private-key"], "read", False),
            (ruleset, ROLE_TARGETS["selector-private-key"], "read", False),
            (ruleset, ROLE_TARGETS["controller-oauth-token"], "read", False),
            (ruleset, ROLE_TARGETS["canary-claude-token"], "read", False),
            (ruleset, "/var/lib/traincapsule-canary-secrets", "read", False),
            (ruleset, "/var/lib/traincapsule-verifier/ruleset-outbox", "write", True),
            (ruleset, "/var/lib/traincapsule-verifier/ruleset", "write", False),
            (refresher, ROLE_TARGETS["github-token-refresher-private-key"], "read", True),
            (refresher, ROLE_TARGETS["github-token-refresher"], "execute", True),
            (refresher, ROLE_TARGETS["git-anchor-updater"], "execute", False),
            (refresher, ROLE_TARGETS["git-anchor-github-private-key"], "read", False),
            (refresher, "/var/lib/traincapsule-github-token/outbox", "write", True),
            (refresher, ROLE_TARGETS["controller-oauth-token"], "read", False),
            (refresher, "/var/lib/traincapsule-canary-secrets", "read", False),
            (fetcher, ROLE_TARGETS["git-anchor-producer"], "execute", True),
            (fetcher, ROLE_TARGETS["git-anchor-askpass"], "execute", True),
            (fetcher, ROLE_TARGETS["git-anchor-github-private-key"], "read", True),
            (fetcher, ROLE_TARGETS["git-anchor-observer-private-key"], "read", True),
            (fetcher, "/var/lib/traincapsule-verifier/anchor-fetcher-inbox", "read", True),
            (fetcher, "/var/lib/traincapsule-verifier/anchor-fetcher-outbox", "write", True),
            (fetcher, "/var/lib/traincapsule-verifier/anchor-updates", "write", False),
            (fetcher, ROLE_TARGETS["private-key"], "read", False),
            (fetcher, ROLE_TARGETS["github-token-refresher-private-key"], "read", False),
        )
        for principal, raw_path, access, expected in checks:
            target = self._target(raw_path)
            if _mode_allows(self.authority, principal, target, access, root=self.root) != expected:
                raise InstallFailure(
                    f"negative access attestation failed: {principal} {access} {raw_path}"
                )
        return len(checks)

    def _target(self, absolute: str) -> Path:
        pure = PurePosixPath(absolute)
        if not pure.is_absolute() or ".." in pure.parts:
            raise InstallFailure("install targets must be normalized absolute paths")
        return self.root.joinpath(*pure.parts[1:])

    def _source(self, relative: str) -> Path:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise InstallFailure("bundle sources must be normalized relative paths")
        root = self.bundle_root.resolve(strict=True)
        source = root.joinpath(*pure.parts)
        resolved = source.resolve(strict=True)
        current = source
        symlinked = False
        while current != root:
            symlinked = symlinked or current.is_symlink()
            current = current.parent
        if symlinked or not resolved.is_relative_to(root) or not resolved.is_file():
            raise InstallFailure("bundle source escapes the distribution or is not regular")
        return resolved

    def _load_state(self) -> None:
        self._state = {}
        path = self.txn / "state.json"
        if path.is_file():
            if path.is_symlink() or path.stat().st_size > 10_000_000:
                raise InstallFailure("transaction state is unsafe")
            expected_owner = (
                self.authority.uid("root"),
                self.authority.gid("root"),
            )
            if (
                self.authority.owner(path) != expected_owner
                or stat.S_IMODE(path.stat().st_mode) != 0o600
            ):
                raise InstallFailure("transaction state ownership or mode is unsafe")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise InstallFailure("transaction state is corrupt")
            self._state = cast(dict[str, object], value)

    def _save_state(self) -> None:
        path = self.txn / "state.json"
        _atomic_replace(path, canonical_json_bytes(self._state), 0o600)
        self.authority.chown(path, "root", "root")
        os.chmod(path, 0o600, follow_symlinks=False)

    def _record(self, event: str, details: dict[str, object]) -> None:
        self.txn.mkdir(parents=True, mode=0o700, exist_ok=True)
        payload = canonical_json_bytes({"event": event, "details": details}) + b"\n"
        event_path = self.txn / "events.jsonl"
        descriptor = os.open(
            event_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise InstallFailure("transaction event journal is not a regular file")
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.authority.chown(event_path, "root", "root")
        os.chmod(event_path, 0o600, follow_symlinks=False)

    def _fail(self, transition: str) -> None:
        if self.fail_hook is not None:
            self.fail_hook(transition)


def _mode_allows(
    authority: AuthorityBackend,
    principal: str,
    path: Path,
    access: str,
    *,
    root: Path,
) -> bool:
    uid = authority.uid(principal)
    gids = authority.groups(principal)

    def allows(target: Path, bit: int) -> bool:
        owner, group = authority.owner(target)
        mode = stat.S_IMODE(target.lstat().st_mode)
        shift = 6 if uid == owner else 3 if group in gids else 0
        return bool((mode >> shift) & bit)

    current = path.parent
    while True:
        if not allows(current, 1):
            return False
        if current == root:
            break
        current = current.parent
    bit = {"read": 4, "write": 2, "execute": 1}[access]
    return allows(path, bit)


def _reject_symlink_parents(path: Path, root: Path) -> None:
    current = path.parent
    while current != root and current != current.parent:
        if current.exists() and current.is_symlink():
            raise InstallFailure(f"symbolic-link parent rejected: {current}")
        current = current.parent
    if root.is_symlink():
        raise InstallFailure("filesystem root cannot be a symbolic link")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _atomic_replace(path: Path, data: bytes, mode: int) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise InstallFailure(f"atomic-write parent is missing or unsafe: {path.parent}")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-privileged-install")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    installer = PrivilegedInstaller.load(args.bundle)
    if args.apply and args.confirm != APPLY_CONFIRMATION:
        parser.error(f"--apply requires --confirm {APPLY_CONFIRMATION}")
    result = installer.apply(args.confirm if args.apply else None)
    if isinstance(result, InstallPreview):
        print(json.dumps({**result.__dict__, "dryRun": True}, sort_keys=True))
    else:
        print(canonical_json_bytes(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
