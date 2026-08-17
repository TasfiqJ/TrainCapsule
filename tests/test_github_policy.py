from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

import tcfactory.github_sync as github_sync
import tcfactory.v3.publication as publication
from tcfactory.github_sync import GitHubConfig, load_github_config
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.contracts_v31 import ActivationMode, ActivationReceiptV31
from tcfactory.v3.publication import (
    ExternalReceiptAuthorizer,
    GhPublicationClient,
    PublicationError,
    trusted_external_path,
)

CANDIDATE = "b" * 40


def test_installed_activation_digests_bind_exact_runtime_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_raw = b'{"installed":"runtime"}\n'
    config_raw = b"runtime: installed\n"
    config_path = tmp_path / "effective-config.yaml"
    config_path.write_bytes(config_raw)
    installed = SimpleNamespace(
        effective_config=SimpleNamespace(
            path=str(config_path), digest=sha256_digest(config_raw)
        )
    )
    def load() -> tuple[Any, bytes]:
        return installed, runtime_raw

    monkeypatch.setattr(github_sync, "load_installed_controller_runtime", load)

    assert github_sync.installed_activation_digests() == (
        sha256_digest(runtime_raw),
        sha256_digest(config_raw),
    )


def test_controller_activation_rejects_substituted_effective_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "effective-config.yaml"
    config_path.write_bytes(b"substituted: true\n")
    installed = SimpleNamespace(
        effective_config=SimpleNamespace(
            path=str(config_path), digest=sha256_digest(b"expected: true\n")
        )
    )
    def load() -> tuple[Any, bytes]:
        return installed, b"{}\n"

    monkeypatch.setattr(github_sync, "load_installed_controller_runtime", load)

    with pytest.raises(github_sync.GitHubSyncError, match="effective config digest"):
        github_sync.installed_activation_digests()


def test_release_controls_use_verified_root_observation_without_gh_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = load_github_config(Path("config/github.yaml"))
    core: dict[str, object] = {
        "repository": config.repository,
        "baseBranch": "main",
        "rulesetId": 20794549,
        "enforcement": "active",
        "requiredCheckAppIds": {},
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": False,
        "directBranchUpdatesForbidden": False,
        "autoMergeEnabled": False,
    }
    digest = sha256_digest(
        (json.dumps(core, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    receipt = tmp_path / "ruleset.json"
    receipt.write_text(json.dumps({**core, "observationDigest": digest}))
    verifier = tmp_path / "verifier"
    verifier.write_text("verified")
    commands: list[list[str]] = []

    def trusted(path: Path, *, directory: bool, label: str) -> tuple[Path, os.stat_result]:
        del directory, label
        return path, path.stat()

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "{}\n", "")

    monkeypatch.setattr(github_sync, "trusted_external_path", trusted)
    monkeypatch.setattr(github_sync, "run_command", run)

    result = github_sync.validate_signed_repository_release_controls(
        config=config, receipt_path=receipt, verifier_path=verifier
    )

    assert result["observationDigest"] == digest
    assert len(commands) == 1
    assert commands[0][0] == str(verifier)


def test_direct_main_publication_is_the_only_active_builder() -> None:
    assert hasattr(github_sync, "build_direct_main_publisher")
    assert not hasattr(github_sync, "build_automated_pr_publisher")
    source = Path(github_sync.__file__).read_text(encoding="utf-8")
    assert "build_direct_main_publisher" in source


def test_direct_main_push_is_exact_non_force_and_race_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        observed.append(args)
        if args[:2] == ["git", "ls-remote"]:
            already_pushed = any("refs/heads/main" in part for part in args) and len(observed) > 2
            sha = CANDIDATE if already_pushed else "a" * 40
            return subprocess.CompletedProcess(args, 0, f"{sha}\trefs/heads/main\n", "")
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(publication, "run_command", fake_run)
    client = GhPublicationClient(
        tmp_path,
        remote="origin",
        repository="TasfiqJ/TrainCapsule",
    )
    with pytest.raises(PublicationError, match="exact commit SHAs"):
        client.push_main(sha="HEAD", expected_base_sha="a" * 40)
    client.push_main(sha=CANDIDATE, expected_base_sha="a" * 40)
    push = next(args for args in observed if args[:2] == ["git", "push"])
    assert push == ["git", "push", "--porcelain", "origin", f"{CANDIDATE}:refs/heads/main"]
    assert all("--force" not in part for part in push)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("directMainPush", False),
        ("releaseMode", "AUTOMATED_PR_REQUIRED_CHECKS_MACHINE_RECEIPT_AUTO_MERGE"),
        ("publisherCapability", "PENDING_PHASE_4"),
        ("mergeQueueOrAutoMergeRequired", True),
    ],
)
def test_v31_config_rejects_legacy_or_unproven_release_modes(field: str, value: object) -> None:
    root = Path(__file__).resolve().parents[1]
    payload = load_github_config(root / "config/github.yaml").model_dump(mode="json", by_alias=True)
    payload[field] = value
    with pytest.raises(ValidationError):
        GitHubConfig.model_validate(payload)


def test_required_check_roster_cannot_omit_independent_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = load_github_config(root / "config/github.yaml").model_dump(mode="json", by_alias=True)
    remote = payload["remoteCi"]
    assert isinstance(remote, dict)
    remote["requiredWorkflows"] = ["TrainCapsule / Factory quality"]
    remote["trustedCheckAppIds"] = {"TrainCapsule / Factory quality": 15368}
    with pytest.raises(ValidationError, match="machine-policy"):
        GitHubConfig.model_validate(payload)


def test_release_rules_allow_only_non_destructive_direct_main_controls() -> None:
    valid = {"non_fast_forward", "deletion"}
    github_sync.validate_release_rule_types(valid)
    with pytest.raises(github_sync.GitHubSyncError, match="incompatible with direct publication"):
        github_sync.validate_release_rule_types(valid | {"pull_request"})
    with pytest.raises(github_sync.GitHubSyncError, match="missing required release controls"):
        github_sync.validate_release_rule_types({"non_fast_forward"})


def test_pull_request_observation_cannot_launder_a_non_main_base() -> None:
    raw: dict[str, object] = {
        "number": 1,
        "url": "https://github.com/TasfiqJ/TrainCapsule/pull/1",
        "state": "OPEN",
        "isDraft": True,
        "headRefName": "factory/v3-rel-001/candidate",
        "headRefOid": CANDIDATE,
        "baseRefName": "attacker-controlled-base",
        "baseRefOid": "a" * 40,
        "mergedAt": None,
        "mergeCommit": None,
        "autoMergeRequest": None,
    }
    with pytest.raises(PublicationError, match="invalid types"):
        GhPublicationClient._pr(raw)  # pyright: ignore[reportPrivateUsage]


def test_external_verifier_paths_reject_symlink_substitution(tmp_path: Path) -> None:
    executable_link = tmp_path / "verifier"
    executable_link.symlink_to("/usr/bin/true")
    with pytest.raises(PublicationError, match="symlink"):
        ExternalReceiptAuthorizer(executable_link)

    receipt_root = tmp_path / "receipts"
    receipt_root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PublicationError, match="symlink"):
        trusted_external_path(receipt_root, directory=True, label="receipt root")


def test_external_activation_authorizer_accepts_strict_canonical_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "verifier"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o555)
    receipt_path = tmp_path / "activation.json"
    now = datetime(2026, 8, 13, 20, 0, tzinfo=UTC)
    receipt = ActivationReceiptV31(
        schema_version="3.1",
        receipt_id="ACT:STRICT-JSON-001",
        verified_main_sha="a" * 40,
        machine_environment_digest="sha256:" + "b" * 64,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "c" * 64,
        controller_binary_digest="sha256:" + "d" * 64,
        controller_config_digest="sha256:" + "e" * 64,
        machine_environment_path="canary-suite.json",
        controller_binary_path="installed-controller-runtime.json",
        controller_config_path="effective-config.yaml",
        machine_policy_receipt_id="MPOL:STRICT-JSON-001",
        machine_policy_receipt_digest="sha256:" + "f" * 64,
        mode=ActivationMode.LIVE,
        issued_at=now,
        expires_at=now + timedelta(minutes=30),
        revocation_epoch=1,
        nonce="strict-json-nonce-0001",
        issuer_id="VERIFIER:INDEPENDENT",
        issuer_key_id="KEY:ED25519:001",
        signature_algorithm="ed25519",
        signature="A" * 80,
    )
    receipt_path.write_bytes(receipt.canonical_json_bytes())

    def trust(
        path: Path, *, directory: bool, label: str
    ) -> tuple[Path, os.stat_result]:
        del directory, label
        return path.resolve(strict=True), path.lstat()

    authorization = publication.PublicActivationAuthorization(
        verified=True,
        verified_main_sha=receipt.verified_main_sha,
        activation_receipt_id=receipt.receipt_id,
        activation_receipt_digest=receipt.canonical_digest(),
    )

    def run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args,
            0,
            authorization.model_dump_json(by_alias=True),
            "",
        )

    monkeypatch.setattr(publication, "trusted_external_path", trust)
    monkeypatch.setattr(publication, "run_command", run)
    observed = ExternalReceiptAuthorizer(executable).verify_activation(
        receipt_path,
        expected_main_sha=receipt.verified_main_sha,
        source_generation_id=receipt.source_generation_id,
        source_generation_digest=receipt.source_generation_digest,
        controller_binary_digest=receipt.controller_binary_digest,
        controller_config_digest=receipt.controller_config_digest,
    )
    assert observed.activation_receipt_digest == receipt.canonical_digest()
