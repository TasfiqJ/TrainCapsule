"""Idempotent staged production-install manifest; no system mutation is performed."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .canonical import canonical_json_bytes, sha256_digest
from .models import StrictModel

SERVICE_USER = "traincapsule-verifier"
BROKER_USER = "root"
CONTROLLER_USER = "traincapsule-controller"


class InstallDirectory(StrictModel):
    path: str
    owner: str
    group: str
    mode: str = Field(pattern=r"^0[0-7]{3}$")
    purpose: str


class InstallFile(StrictModel):
    path: str
    owner: str
    group: str
    mode: str = Field(pattern=r"^0[0-7]{3}$")
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    purpose: str


class AccessAssertion(StrictModel):
    principal: str
    path: str
    access: Literal["read", "write", "execute"]
    allowed: bool


class RollbackStep(StrictModel):
    order: int = Field(gt=0)
    action: Literal["stop", "disable", "restore", "remove-if-empty", "retain"]
    target: str
    reason: str


class InstallManifest(StrictModel):
    schema_version: Literal["3.1"] = "3.1"
    state: Literal["STAGED_NOT_ACTIVATED"] = "STAGED_NOT_ACTIVATED"
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    service_user: Literal["traincapsule-verifier"] = SERVICE_USER
    controller_user: Literal["traincapsule-controller"] = CONTROLLER_USER
    directories: list[InstallDirectory]
    files: list[InstallFile]
    access_assertions: list[AccessAssertion]
    rollback: list[RollbackStep]
    live_credentials_installed: Literal[False] = False
    live_oracles_installed: Literal[False] = False
    system_mutated: Literal[False] = False

    @model_validator(mode="after")
    def validate_separation(self) -> InstallManifest:
        required_denials = {
            (CONTROLLER_USER, "/var/lib/traincapsule-verifier/private", "read", False),
            (CONTROLLER_USER, "/var/lib/traincapsule-verifier/oracle", "execute", False),
            (CONTROLLER_USER, "/var/lib/traincapsule-verifier/outbox", "read", False),
            (CONTROLLER_USER, "/usr/libexec/traincapsule-verifier-issuer", "execute", False),
            (SERVICE_USER, "/var/lib/traincapsule-verifier/receipts", "write", False),
            (CONTROLLER_USER, "/var/lib/traincapsule-verifier/inbox", "write", False),
            (CONTROLLER_USER, "/var/lib/traincapsule-verifier/request-journal", "read", False),
        }
        actual = {
            (item.principal, item.path, item.access, item.allowed)
            for item in self.access_assertions
        }
        if not required_denials <= actual:
            raise ValueError("install manifest omits required authority-separation denials")
        return self


UnitKind = Literal[
    "issuer",
    "issuer-path",
    "activation-issuer",
    "activation-path",
    "receipt-broker",
    "receipt-path",
    "request-broker",
    "request-path",
    "check-worker",
    "check-path",
    "selector",
    "selector-path",
    "selector-broker",
    "selector-broker-path",
    "activation-request-broker",
    "activation-request-path",
    "activation-supervisor",
    "activation-supervisor-timer",
    "controller-start-broker",
    "controller-start-path",
    "post-activation-observer",
    "post-activation-observer-timer",
    "ruleset-observer",
    "ruleset-observer-timer",
    "ruleset-broker",
    "ruleset-broker-path",
    "git-anchor-updater",
    "git-anchor-updater-path",
    "git-anchor-job-broker",
    "git-anchor-job-broker-path",
    "git-anchor-producer",
    "git-anchor-producer-path",
    "git-anchor-promoter",
    "git-anchor-promoter-path",
]


def systemd_unit_content(
    *, unit: UnitKind, controller_user: str = CONTROLLER_USER
) -> bytes:
    """Render one exact production unit without mutating the host."""
    if not controller_user or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
        for character in controller_user
    ):
        raise ValueError("controller service principal is invalid")
    if unit == "activation-supervisor":
        value = f"""[Unit]
Description=TrainCapsule stopped-state activation supervisor
After=network-online.target traincapsule-verifier-ruleset-broker.service
Wants=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=4h
User={controller_user}
Group={controller_user}
EnvironmentFile=/etc/traincapsule-controller/controller-runtime.env
ExecStart=/usr/libexec/traincapsule-activation-supervisor
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
# The controller principal has exactly one sudoers allowlist entry for the
# root-owned private-gate helper.  Setting NoNewPrivileges=yes here prevents
# that fail-closed health probe from executing at all.
NoNewPrivileges=no
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadOnlyPaths=/var/lib/traincapsule-verifier/receipts
ReadWritePaths=/var/lib/traincapsule-runtime
ReadWritePaths=/var/lib/traincapsule-verifier/controller-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/activation-controller-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/controller-start-outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "controller-start-broker":
        value = """[Unit]
Description=TrainCapsule receipt-gated controller start broker
After=traincapsule-verifier-activation-selector-broker.service

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-controller-start process-outbox
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadOnlyPaths=/var/lib/traincapsule-verifier/controller-start-outbox
ReadOnlyPaths=/var/lib/traincapsule-verifier/activation
ReadOnlyPaths=/var/lib/traincapsule-verifier/receipts
ReadWritePaths=/var/lib/traincapsule-runtime
ReadWritePaths=/var/lib/traincapsule-verifier/controller-start-journal
InaccessiblePaths=/var/lib/traincapsule-verifier/private
InaccessiblePaths=/var/lib/traincapsule-verifier/oracle
"""
    elif unit == "controller-start-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/controller-start-outbox
Unit=traincapsule-verifier-controller-start.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "post-activation-observer":
        value = """[Unit]
Description=TrainCapsule independent post-activation observer
After=traincapsule-controller.service traincapsule-verifier-controller-start.service
ConditionPathExists=/var/lib/traincapsule-verifier/activation/current.json

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-post-activation observe
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier /etc/traincapsule-controller
ReadOnlyPaths=/var/lib/traincapsule-verifier/activation
ReadOnlyPaths=/var/lib/traincapsule-verifier/controller-start-journal
ReadOnlyPaths=/var/lib/traincapsule-runtime
ReadWritePaths=/var/lib/traincapsule-verifier/post-activation-observations
ReadWritePaths=/var/lib/traincapsule-verifier/activation-refresh-inbox
ReadWritePaths=/var/lib/traincapsule-verifier/activation-refresh-retirement
ReadWritePaths=/var/lib/traincapsule-runtime
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "post-activation-observer-timer":
        value = """[Timer]
OnBootSec=2m
OnCalendar=*-*-* *:00/2:00
Persistent=true
Unit=traincapsule-verifier-post-activation-observer.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "activation-supervisor-timer":
        value = """[Timer]
OnBootSec=1m
OnCalendar=*-*-* *:00/5:00
Persistent=true
Unit=traincapsule-activation-supervisor.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "git-anchor-updater":
        value = """[Unit]
Description=TrainCapsule root exact-main Git anchor updater
After=traincapsule-verifier-observed-main-selector.service

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-git-anchor-updater process-inbox
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadOnlyPaths=/var/lib/traincapsule-verifier/anchor-updates
ReadWritePaths=/var/lib/traincapsule-runtime/git
ReadWritePaths=/var/lib/traincapsule-verifier/anchor-update-journal
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "git-anchor-updater-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/anchor-updates
Unit=traincapsule-verifier-git-anchor-updater.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "git-anchor-job-broker":
        value = """[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-git-anchor-producer stage-jobs
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadOnlyPaths=/var/lib/traincapsule-runtime/publication-transactions
ReadWritePaths=/var/lib/traincapsule-verifier/anchor-fetcher-inbox
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "git-anchor-job-broker-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-runtime/publication-transactions
Unit=traincapsule-verifier-git-anchor-job-broker.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "git-anchor-producer":
        value = """[Unit]
Description=TrainCapsule read-only GitHub App exact-main bundle producer
After=network-online.target traincapsule-verifier-git-anchor-job-broker.service
Wants=network-online.target

[Service]
Type=oneshot
User=traincapsule-anchor-fetcher
Group=traincapsule-anchor-fetcher
ExecStart=/usr/libexec/traincapsule-verifier-git-anchor-producer produce
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=/etc/traincapsule-verifier
ReadOnlyPaths=/var/lib/traincapsule-verifier/anchor-fetcher-private
ReadOnlyPaths=/var/lib/traincapsule-verifier/ruleset
ReadWritePaths=/var/lib/traincapsule-verifier/anchor-fetcher-outbox
InaccessiblePaths=/var/lib/traincapsule-runtime /var/lib/traincapsule-verifier/private
"""
    elif unit == "git-anchor-producer-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/anchor-fetcher-inbox
Unit=traincapsule-verifier-git-anchor-producer.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "git-anchor-promoter":
        value = """[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-git-anchor-producer promote
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadOnlyPaths=/var/lib/traincapsule-verifier/anchor-fetcher-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/anchor-updates
InaccessiblePaths=/var/lib/traincapsule-runtime /var/lib/traincapsule-verifier/private
"""
    elif unit == "git-anchor-promoter-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/anchor-fetcher-outbox
Unit=traincapsule-verifier-git-anchor-promoter.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "activation-request-broker":
        value = """[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-activation-request-broker process-outbox
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/var/lib/traincapsule-verifier/activation-controller-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/activation-requests
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "activation-request-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/activation-controller-outbox
Unit=traincapsule-verifier-activation-request-broker.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "ruleset-observer":
        value = """[Unit]
Description=TrainCapsule independent GitHub ruleset observer
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=traincapsule-ruleset-observer
Group=traincapsule-ruleset-observer
EnvironmentFile=/etc/traincapsule-verifier/ruleset-observer-credential.env
ExecStart=/usr/libexec/traincapsule-verifier-ruleset-observer observe
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadWritePaths=/var/lib/traincapsule-verifier/ruleset-outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/receipts
"""
    elif unit == "ruleset-observer-timer":
        value = """[Unit]
Description=TrainCapsule bounded ruleset observation refresh

[Timer]
OnBootSec=30s
OnCalendar=*-*-* *:00/5:00
RandomizedDelaySec=30s
Persistent=true
Unit=traincapsule-verifier-ruleset-observer.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "ruleset-broker":
        value = """[Unit]
After=traincapsule-verifier-ruleset-observer.service

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-ruleset-broker process-outbox
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier /var/lib/traincapsule-verifier/ruleset-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/ruleset
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "ruleset-broker-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/ruleset-outbox
Unit=traincapsule-verifier-ruleset-broker.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "selector":
        value = """[Unit]
Description=TrainCapsule independent observed-main selector
Requires=traincapsule-verifier-ruleset-observer.service traincapsule-verifier-ruleset-broker.service
After=network-online.target traincapsule-verifier-ruleset-observer.service
After=traincapsule-verifier-ruleset-broker.service
Wants=network-online.target

[Service]
Type=oneshot
User=traincapsule-selector
Group=traincapsule-selector
EnvironmentFile=/etc/traincapsule-verifier/selector-credential.env
ExecStart=/usr/libexec/traincapsule-verifier-observed-main-selector process-requests
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadOnlyPaths=/var/lib/traincapsule-verifier/activation-requests
ReadOnlyPaths=/var/lib/traincapsule-verifier/ruleset
ReadWritePaths=/var/lib/traincapsule-verifier/selector-outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/private
InaccessiblePaths=/var/lib/traincapsule-verifier/outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/receipts
"""
    elif unit == "selector-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/activation-requests
Unit=traincapsule-verifier-observed-main-selector.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "selector-broker":
        value = """[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-activation-selector-broker process-outbox
NoNewPrivileges=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier /var/lib/traincapsule-verifier/selector-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/activation-inbox
InaccessiblePaths=/var/lib/traincapsule-verifier/private /var/lib/traincapsule-verifier/oracle
"""
    elif unit == "selector-broker-path":
        value = """[Path]
PathChanged=/var/lib/traincapsule-verifier/selector-outbox
Unit=traincapsule-verifier-activation-selector-broker.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "check-path":
        value = """[Unit]
Description=TrainCapsule GitHub App check trigger

[Path]
PathChanged=/var/lib/traincapsule-verifier/receipts
Unit=traincapsule-verifier-check-worker.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "activation-issuer":
        value = """[Unit]
Description=TrainCapsule independent activation issuer

[Service]
Type=oneshot
User=traincapsule-verifier
Group=traincapsule-verifier
ExecStart=/usr/libexec/traincapsule-verifier-activation-issuer process-inbox
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadWritePaths=/var/lib/traincapsule-verifier/state /var/lib/traincapsule-verifier/outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/receipts
"""
    elif unit == "activation-path":
        value = """[Unit]
Description=TrainCapsule activation issuance trigger

[Path]
PathChanged=/var/lib/traincapsule-verifier/activation-inbox
Unit=traincapsule-verifier-activation-issuer.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "check-worker":
        value = """[Unit]
Description=TrainCapsule GitHub App machine-policy check worker
After=network-online.target traincapsule-verifier-broker.service
Wants=network-online.target

[Service]
Type=oneshot
User=traincapsule-verifier
Group=traincapsule-verifier
ExecStart=/usr/libexec/traincapsule-verifier-check-worker process-receipts
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier /var/lib/traincapsule-verifier/receipts
ReadWritePaths=/var/lib/traincapsule-verifier/check-journal
InaccessiblePaths=/var/lib/traincapsule-verifier/private/signing-key.pem
"""
    elif unit == "receipt-broker":
        value = """[Unit]
Description=TrainCapsule root receipt broker
After=traincapsule-verifier-issuer.service

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-broker process-outbox
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier /var/lib/traincapsule-verifier/outbox
ReadWritePaths=/var/lib/traincapsule-verifier/receipts /var/lib/traincapsule-verifier/activation

[Install]
WantedBy=multi-user.target
"""
    elif unit == "receipt-path":
        value = """[Unit]
Description=TrainCapsule receipt promotion trigger

[Path]
PathChanged=/var/lib/traincapsule-verifier/outbox
Unit=traincapsule-verifier-broker.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "request-broker":
        value = """[Unit]
Description=TrainCapsule root request validation broker

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/libexec/traincapsule-verifier-request-broker process-outbox
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/var/lib/traincapsule-verifier/controller-outbox
ReadWritePaths=/var/lib/traincapsule-verifier/inbox /var/lib/traincapsule-verifier/request-journal
InaccessiblePaths=/var/lib/traincapsule-verifier/private
InaccessiblePaths=/var/lib/traincapsule-verifier/oracle
InaccessiblePaths=/var/lib/traincapsule-verifier/outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/receipts

[Install]
WantedBy=multi-user.target
"""
    elif unit == "issuer-path":
        value = """[Unit]
Description=TrainCapsule independent issuer trigger

[Path]
PathChanged=/var/lib/traincapsule-verifier/inbox
Unit=traincapsule-verifier-issuer.service

[Install]
WantedBy=multi-user.target
"""
    elif unit == "request-path":
        value = """[Unit]
Description=TrainCapsule request broker trigger

[Path]
PathChanged=/var/lib/traincapsule-verifier/controller-outbox
Unit=traincapsule-verifier-request-broker.service

[Install]
WantedBy=multi-user.target
"""
    else:
        value = """[Unit]
Description=TrainCapsule independent receipt issuer

[Service]
Type=oneshot
User=traincapsule-verifier
Group=traincapsule-verifier
ExecStart=/usr/libexec/traincapsule-verifier-issuer process-inbox
WorkingDirectory=/var/lib/traincapsule-verifier/repository-boundary
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/etc/traincapsule-verifier
ReadWritePaths=/var/lib/traincapsule-verifier/state /var/lib/traincapsule-verifier/outbox
InaccessiblePaths=/var/lib/traincapsule-verifier/receipts

[Install]
WantedBy=multi-user.target
"""
    return value.encode()


def _manifest_digest(manifest: InstallManifest) -> str:
    payload = manifest.model_dump(mode="json", by_alias=True)
    payload["manifestDigest"] = "sha256:" + "0" * 64
    return sha256_digest(canonical_json_bytes(payload))


def controller_start_policy_content() -> bytes:
    return canonical_json_bytes(
        {
            "schemaVersion": "3.1",
            "controllerPrincipal": CONTROLLER_USER,
            "serviceName": "traincapsule-controller.service",
            "repositoryRoot": "/var/lib/traincapsule-verifier/repository-boundary",
            "runtimeRoot": "/var/lib/traincapsule-runtime",
            "runtimeManifestPath": "/etc/traincapsule-controller/runtime-manifest.json",
            "journalRoot": "/var/lib/traincapsule-verifier/controller-start-journal",
        }
    )


def post_activation_policy_content() -> bytes:
    return canonical_json_bytes(
        {
            "schemaVersion": "3.1",
            "serviceName": "traincapsule-controller.service",
            "repositoryRoot": "/var/lib/traincapsule-verifier/repository-boundary",
            "runtimeRoot": "/var/lib/traincapsule-runtime",
            "startJournalRoot": "/var/lib/traincapsule-verifier/controller-start-journal",
            "observationRoot": (
                "/var/lib/traincapsule-verifier/post-activation-observations"
            ),
            "refreshCompletionRoot": (
                "/var/lib/traincapsule-verifier/activation-refresh-inbox"
            ),
            "refreshRetirementRoot": (
                "/var/lib/traincapsule-verifier/activation-refresh-retirement"
            ),
            "runtimeManifestPath": (
                "/etc/traincapsule-controller/runtime-manifest.json"
            ),
            "maximumObservationSeconds": 3600,
        }
    )


def git_anchor_policy_content() -> bytes:
    return canonical_json_bytes(
        {
            "schemaVersion": "3.1",
            "repository": "TasfiqJ/TrainCapsule",
            "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
            "sourceGenerationDigest": (
                "sha256:06b0e62f960bf4fe2e87d457d92bafda392e7369ee6a576d9ca36530b9f4263c"
            ),
            "anchorRoot": "/var/lib/traincapsule-runtime/git",
            "transactionRoot": "/var/lib/traincapsule-verifier/anchor-update-journal",
        }
    )


def git_anchor_producer_policy_content() -> bytes:
    return canonical_json_bytes(
        {
            "schemaVersion": "3.1",
            "repository": "TasfiqJ/TrainCapsule",
            "githubAppId": 0,
            "installationId": 0,
            "permissions": {
                "checks": "read",
                "contents": "read",
                "pull_requests": "read",
            },
            "requiredCheckAppIds": {
                "TrainCapsule / Factory quality": 15368,
                "TrainCapsule / Product unit": 15368,
                "TrainCapsule / Product contract": 15368,
                "TrainCapsule / Security": 15368,
                "TrainCapsule / Source-of-truth integrity": 15368,
                "TrainCapsule / Packaging install": 15368,
                "TrainCapsule / Docs and schemas": 15368,
                "TrainCapsule / Source freshness": 15368,
                "TrainCapsule / Machine policy": 0,
            },
            "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
            "sourceGenerationDigest": (
                "sha256:06b0e62f960bf4fe2e87d457d92bafda392e7369ee6a576d9ca36530b9f4263c"
            ),
            "privateKeyPath": (
                "/var/lib/traincapsule-verifier/anchor-fetcher-private/"
                "github-app-private-key.pem"
            ),
            "observerKeyPath": (
                "/var/lib/traincapsule-verifier/anchor-fetcher-private/"
                "observer-private-key.pem"
            ),
            "rulesetReceiptPath": "/var/lib/traincapsule-verifier/ruleset/current.json",
            "rulesetPublicKeyPath": "/etc/traincapsule-verifier/ruleset-public-key.pem",
        }
    )


def production_install_manifest() -> InstallManifest:
    """Return the exact inert plan a privileged installer must apply and attest."""

    directories = [
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/anchor-fetcher-inbox",
            owner="traincapsule-anchor-fetcher",
            group="traincapsule-anchor-fetcher",
            mode="0700",
            purpose="root-brokered exact merged-main jobs",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/anchor-fetcher-outbox",
            owner="traincapsule-anchor-fetcher",
            group="traincapsule-anchor-fetcher",
            mode="0700",
            purpose="unsigned exact Git bundle/evidence output",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/anchor-fetcher-private",
            owner="traincapsule-anchor-fetcher",
            group="traincapsule-anchor-fetcher",
            mode="0700",
            purpose="dedicated read-only GitHub App and observer keys",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/anchor-updates",
            owner="root",
            group="root",
            mode="0700",
            purpose="root-brokered observed-main receipts and exact Git bundles",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/anchor-update-journal",
            owner="root",
            group="root",
            mode="0700",
            purpose="root exact-main anchor advancement journal",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/controller-start-outbox",
            owner=CONTROLLER_USER,
            group=CONTROLLER_USER,
            mode="0700",
            purpose="controller-owned unsigned post-activation start requests",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/controller-start-journal",
            owner="root",
            group="root",
            mode="0700",
            purpose="root controller-start transaction journal",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/post-activation-observations",
            owner="root",
            group="root",
            mode="0700",
            purpose="independent post-activation observations and stop journals",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/activation-refresh-retirement",
            owner="root",
            group="root",
            mode="0700",
            purpose="root refresh completion retirement journal and archive",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/activation-controller-outbox",
            owner=CONTROLLER_USER,
            group=CONTROLLER_USER,
            mode="0700",
            purpose="controller-owned unsigned activation requests and bound evidence",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/ruleset-outbox",
            owner="traincapsule-ruleset-observer",
            group="traincapsule-ruleset-observer",
            mode="0700",
            purpose="versioned signed ruleset observations awaiting root promotion",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/ruleset-private",
            owner="traincapsule-ruleset-observer",
            group="traincapsule-ruleset-observer",
            mode="0700",
            purpose="ruleset-observer-only signing key",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/ruleset",
            owner="root",
            group="root",
            mode="0755",
            purpose="root-selected ruleset observation history and current selector",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/activation-requests",
            owner="traincapsule-selector",
            group="traincapsule-selector",
            mode="0700",
            purpose="activation requests awaiting independent exact-main observation",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/selector-outbox",
            owner="traincapsule-selector",
            group="traincapsule-selector",
            mode="0700",
            purpose="selector-signed envelopes awaiting root copy broker",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/selector-private",
            owner="traincapsule-selector",
            group="traincapsule-selector",
            mode="0700",
            purpose="selector-only signing key",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/activation-inbox",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="selector-signed activation request intake",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/activation",
            owner="root",
            group="root",
            mode="0755",
            purpose="root-selected current activation receipt",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/check-journal",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="GitHub App check delivery reconciliation",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/repository-boundary",
            owner="root",
            group="root",
            mode="0555",
            purpose=(
                "fixed trust-boundary anchor; request evidence binds the candidate SHA and tree"
            ),
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier",
            owner="root",
            group="root",
            mode="0755",
            purpose="public authority and receipt parent",
        ),
        InstallDirectory(
            path="/etc/traincapsule-verifier",
            owner="root",
            group="root",
            mode="0755",
            purpose="public policy and key",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/state",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="issuer nonce state",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/private",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="private signing key",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/oracle",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="private oracle executables",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/outbox",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="signed service output",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/inbox",
            owner=SERVICE_USER,
            group=SERVICE_USER,
            mode="0700",
            purpose="service-owned verified request inbox",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/controller-outbox",
            owner=CONTROLLER_USER,
            group=CONTROLLER_USER,
            mode="0700",
            purpose="controller-owned canonical request submission",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/request-journal",
            owner="root",
            group="root",
            mode="0700",
            purpose="root request-broker idempotency journal",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/receipts",
            owner="root",
            group="root",
            mode="0755",
            purpose="root-promoted public receipts",
        ),
        InstallDirectory(
            path="/var/lib/traincapsule-verifier/journal",
            owner="root",
            group="root",
            mode="0700",
            purpose="broker idempotency state",
        ),
    ]
    units = (
        (
            "/etc/systemd/system/traincapsule-activation-supervisor.service",
            systemd_unit_content(unit="activation-supervisor"),
            "zero-human stopped-state canary and activation request supervisor",
        ),
        (
            "/etc/systemd/system/traincapsule-activation-supervisor.timer",
            systemd_unit_content(unit="activation-supervisor-timer"),
            "bounded automatic stopped-state activation retry",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-controller-start.service",
            systemd_unit_content(unit="controller-start-broker"),
            "root-only signed-receipt controller start broker",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-controller-start.path",
            systemd_unit_content(unit="controller-start-path"),
            "automatic controller start request trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-post-activation-observer.service",
            systemd_unit_content(unit="post-activation-observer"),
            "independent seven-event live autonomy observer",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-post-activation-observer.timer",
            systemd_unit_content(unit="post-activation-observer-timer"),
            "bounded automatic post-activation observation",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-activation-request-broker.service",
            systemd_unit_content(unit="activation-request-broker"),
            "copy-only activation request validation broker",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-activation-request-broker.path",
            systemd_unit_content(unit="activation-request-path"),
            "automatic activation request intake",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-ruleset-observer.service",
            systemd_unit_content(unit="ruleset-observer"),
            "independent read-only GitHub ruleset observer",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-ruleset-observer.timer",
            systemd_unit_content(unit="ruleset-observer-timer"),
            "bounded autonomous ruleset observation refresh",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-ruleset-broker.service",
            systemd_unit_content(unit="ruleset-broker"),
            "root ruleset observation selector",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-ruleset-broker.path",
            systemd_unit_content(unit="ruleset-broker-path"),
            "automatic ruleset observation promotion",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-updater.service",
            systemd_unit_content(unit="git-anchor-updater"),
            "root exact-main Git anchor updater",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-updater.path",
            systemd_unit_content(unit="git-anchor-updater-path"),
            "automatic root-brokered Git anchor advancement",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-job-broker.service",
            systemd_unit_content(unit="git-anchor-job-broker"),
            "root controller-transaction to fetch-job broker",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-job-broker.path",
            systemd_unit_content(unit="git-anchor-job-broker-path"),
            "automatic merged transaction intake",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-producer.service",
            systemd_unit_content(unit="git-anchor-producer"),
            "read-only GitHub App exact-main bundle producer",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-producer.path",
            systemd_unit_content(unit="git-anchor-producer-path"),
            "automatic fetch job trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-promoter.service",
            systemd_unit_content(unit="git-anchor-promoter"),
            "root content-bound bundle promoter",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-git-anchor-promoter.path",
            systemd_unit_content(unit="git-anchor-promoter-path"),
            "automatic bundle promotion trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-issuer.service",
            systemd_unit_content(unit="issuer"),
            "service-only issuer",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-issuer.path",
            systemd_unit_content(unit="issuer-path"),
            "automatic issuer trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-activation-issuer.service",
            systemd_unit_content(unit="activation-issuer"),
            "selector-gated activation issuer",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-activation-issuer.path",
            systemd_unit_content(unit="activation-path"),
            "automatic activation issuance trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-check-worker.service",
            systemd_unit_content(unit="check-worker"),
            "credential-gated GitHub App check publisher",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-check-worker.path",
            systemd_unit_content(unit="check-path"),
            "automatic GitHub App check trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-observed-main-selector.service",
            systemd_unit_content(unit="selector"),
            "independent exact-main/check/ruleset selector",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-observed-main-selector.path",
            systemd_unit_content(unit="selector-path"),
            "automatic exact-main selector trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-activation-selector-broker.service",
            systemd_unit_content(unit="selector-broker"),
            "copy-only root activation selector broker",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-activation-selector-broker.path",
            systemd_unit_content(unit="selector-broker-path"),
            "automatic selector-envelope broker trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-broker.service",
            systemd_unit_content(unit="receipt-broker"),
            "minimal root broker",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-broker.path",
            systemd_unit_content(unit="receipt-path"),
            "automatic receipt promotion trigger",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-request-broker.service",
            systemd_unit_content(unit="request-broker"),
            "copy-only root request broker",
        ),
        (
            "/etc/systemd/system/traincapsule-verifier-request-broker.path",
            systemd_unit_content(unit="request-path"),
            "automatic request broker trigger",
        ),
    )
    files = [
        InstallFile(
            path=path,
            owner="root",
            group="root",
            mode="0644",
            content_digest=sha256_digest(content),
            purpose=purpose,
        )
        for path, content, purpose in units
    ]
    controller_policy = canonical_json_bytes(
        {"schemaVersion": "3.1", "principal": CONTROLLER_USER}
    )
    files.append(
        InstallFile(
            path="/etc/traincapsule-verifier/controller-principal.json",
            owner="root",
            group="root",
            mode="0644",
            content_digest=sha256_digest(controller_policy),
            purpose="single root-owned controller principal binding",
        )
    )
    controller_start_policy = controller_start_policy_content()
    files.append(
        InstallFile(
            path="/etc/traincapsule-verifier/controller-start-policy.json",
            owner="root",
            group="root",
            mode="0644",
            content_digest=sha256_digest(controller_start_policy),
            purpose="exact controller service and runtime start binding",
        )
    )
    post_activation_policy = post_activation_policy_content()
    files.append(
        InstallFile(
            path="/etc/traincapsule-verifier/post-activation-policy.json",
            owner="root",
            group="root",
            mode="0644",
            content_digest=sha256_digest(post_activation_policy),
            purpose="exact independent seven-event post-activation observation policy",
        )
    )
    anchor_policy = git_anchor_policy_content()
    files.append(
        InstallFile(
            path="/etc/traincapsule-verifier/git-anchor-policy.json",
            owner="root",
            group="root",
            mode="0644",
            content_digest=sha256_digest(anchor_policy),
            purpose="exact observed-main Git anchor update policy template",
        )
    )
    producer_policy = git_anchor_producer_policy_content()
    files.append(
        InstallFile(
            path="/etc/traincapsule-verifier/git-anchor-producer-policy.json",
            owner="root",
            group="root",
            mode="0444",
            content_digest=sha256_digest(producer_policy),
            purpose=(
                "read-only GitHub App identity/scope and exact source/check binding template; "
                "zero App IDs deliberately fail closed until externally provisioned"
            ),
        )
    )
    assertions = [
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/private",
            access="read",
            allowed=False,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/controller-outbox",
            access="write",
            allowed=True,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/controller-start-outbox",
            access="write",
            allowed=True,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/inbox",
            access="write",
            allowed=False,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/request-journal",
            access="read",
            allowed=False,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/oracle",
            access="execute",
            allowed=False,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/var/lib/traincapsule-verifier/outbox",
            access="read",
            allowed=False,
        ),
        AccessAssertion(
            principal=CONTROLLER_USER,
            path="/usr/libexec/traincapsule-verifier-issuer",
            access="execute",
            allowed=False,
        ),
        AccessAssertion(
            principal=SERVICE_USER,
            path="/var/lib/traincapsule-verifier/receipts",
            access="write",
            allowed=False,
        ),
        AccessAssertion(
            principal=BROKER_USER,
            path="/var/lib/traincapsule-verifier/outbox",
            access="read",
            allowed=True,
        ),
        AccessAssertion(
            principal=BROKER_USER,
            path="/var/lib/traincapsule-verifier/receipts",
            access="write",
            allowed=True,
        ),
    ]
    rollback = [
        RollbackStep(
            order=1,
            action="stop",
            target="traincapsule-verifier-request-broker.path",
            reason="stop controller request intake before rollback",
        ),
        RollbackStep(
            order=2,
            action="stop",
            target="traincapsule-verifier-issuer.path",
            reason="stop issuer triggers before rollback",
        ),
        RollbackStep(
            order=3,
            action="stop",
            target="traincapsule-verifier-broker.path",
            reason="stop receipt promotion triggers before rollback",
        ),
        RollbackStep(
            order=4,
            action="stop",
            target="traincapsule-verifier-issuer.service",
            reason="stop in-flight signing",
        ),
        RollbackStep(
            order=5,
            action="disable",
            target="traincapsule-verifier-request-broker.path",
            reason="prevent request broker restart",
        ),
        RollbackStep(
            order=6,
            action="disable",
            target="traincapsule-verifier-issuer.path",
            reason="prevent issuer restart",
        ),
        RollbackStep(
            order=7,
            action="disable",
            target="traincapsule-verifier-broker.path",
            reason="prevent promotion restart",
        ),
        RollbackStep(
            order=8,
            action="retain",
            target="/var/lib/traincapsule-verifier/receipts",
            reason="preserve public audit evidence",
        ),
        RollbackStep(
            order=9,
            action="retain",
            target="/var/lib/traincapsule-verifier/outbox",
            reason="preserve unpromoted forensic evidence",
        ),
        RollbackStep(
            order=10,
            action="remove-if-empty",
            target="/var/lib/traincapsule-verifier/private",
            reason="remove only after independent key revocation and backup",
        ),
    ]
    provisional = InstallManifest(
        manifest_digest="sha256:" + "0" * 64,
        directories=directories,
        files=files,
        access_assertions=assertions,
        rollback=rollback,
    )
    return provisional.model_copy(update={"manifest_digest": _manifest_digest(provisional)})


def render_systemd_units(destination: Path) -> Sequence[Path]:
    """Write units only into a caller-supplied empty staging directory."""

    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise ValueError("installer staging destination must be absent or empty")
    else:
        destination.mkdir(parents=True, mode=0o700)
    rendered: list[Path] = []
    units_to_render: tuple[tuple[str, UnitKind], ...] = (
        ("traincapsule-activation-supervisor.service", "activation-supervisor"),
        ("traincapsule-activation-supervisor.timer", "activation-supervisor-timer"),
        ("traincapsule-verifier-controller-start.service", "controller-start-broker"),
        ("traincapsule-verifier-controller-start.path", "controller-start-path"),
        (
            "traincapsule-verifier-post-activation-observer.service",
            "post-activation-observer",
        ),
        (
            "traincapsule-verifier-post-activation-observer.timer",
            "post-activation-observer-timer",
        ),
        (
            "traincapsule-verifier-activation-request-broker.service",
            "activation-request-broker",
        ),
        ("traincapsule-verifier-activation-request-broker.path", "activation-request-path"),
        ("traincapsule-verifier-ruleset-observer.service", "ruleset-observer"),
        ("traincapsule-verifier-ruleset-observer.timer", "ruleset-observer-timer"),
        ("traincapsule-verifier-ruleset-broker.service", "ruleset-broker"),
        ("traincapsule-verifier-ruleset-broker.path", "ruleset-broker-path"),
        ("traincapsule-verifier-git-anchor-updater.service", "git-anchor-updater"),
        ("traincapsule-verifier-git-anchor-updater.path", "git-anchor-updater-path"),
        ("traincapsule-verifier-git-anchor-job-broker.service", "git-anchor-job-broker"),
        ("traincapsule-verifier-git-anchor-job-broker.path", "git-anchor-job-broker-path"),
        ("traincapsule-verifier-git-anchor-producer.service", "git-anchor-producer"),
        ("traincapsule-verifier-git-anchor-producer.path", "git-anchor-producer-path"),
        ("traincapsule-verifier-git-anchor-promoter.service", "git-anchor-promoter"),
        ("traincapsule-verifier-git-anchor-promoter.path", "git-anchor-promoter-path"),
        ("traincapsule-verifier-issuer.service", "issuer"),
        ("traincapsule-verifier-issuer.path", "issuer-path"),
        ("traincapsule-verifier-activation-issuer.service", "activation-issuer"),
        ("traincapsule-verifier-activation-issuer.path", "activation-path"),
        ("traincapsule-verifier-check-worker.service", "check-worker"),
        ("traincapsule-verifier-check-worker.path", "check-path"),
        ("traincapsule-verifier-observed-main-selector.service", "selector"),
        ("traincapsule-verifier-observed-main-selector.path", "selector-path"),
        ("traincapsule-verifier-activation-selector-broker.service", "selector-broker"),
        ("traincapsule-verifier-activation-selector-broker.path", "selector-broker-path"),
        ("traincapsule-verifier-broker.service", "receipt-broker"),
        ("traincapsule-verifier-broker.path", "receipt-path"),
        ("traincapsule-verifier-request-broker.service", "request-broker"),
        ("traincapsule-verifier-request-broker.path", "request-path"),
    )
    for name, unit in units_to_render:
        target = destination / name
        target.write_bytes(systemd_unit_content(unit=unit))
        target.chmod(0o600)
        rendered.append(target)
    manifest = production_install_manifest()
    manifest_path = destination / "install-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    manifest_path.chmod(0o600)
    rendered.append(manifest_path)
    return tuple(rendered)


def staged_tree_digest(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        data = path.read_bytes()
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(data)
    return "sha256:" + digest.hexdigest()
