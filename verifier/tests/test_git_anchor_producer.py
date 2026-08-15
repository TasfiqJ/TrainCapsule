from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from traincapsule_verifier import git_anchor_producer as producer
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.crypto import sign_model
from traincapsule_verifier.git_anchor_producer import AnchorProducerPolicy
from traincapsule_verifier.git_anchor_updater import AnchorUpdatePolicy, advance_anchor
from traincapsule_verifier.models import (
    RulesetObservationReceipt,
    ruleset_observation_identifier,
)

NOW = datetime(2026, 8, 12, 22, 0, tzinfo=UTC)


def _git(path: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def _private_raw(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_raw(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _policy() -> AnchorProducerPolicy:
    return AnchorProducerPolicy(
        repository="TasfiqJ/TrainCapsule",
        github_app_id=900001,
        installation_id=700001,
        permissions={"checks": "read", "contents": "read", "pull_requests": "read"},
        required_check_app_ids={
            "TrainCapsule / Factory quality": 15368,
            "TrainCapsule / Machine policy": 900002,
        },
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "a" * 64,
        private_key_path=(
            "/var/lib/traincapsule-verifier/anchor-fetcher-private/"
            "github-app-private-key.pem"
        ),
        observer_key_path=(
            "/var/lib/traincapsule-verifier/anchor-fetcher-private/"
            "observer-private-key.pem"
        ),
        ruleset_receipt_path="/var/lib/traincapsule-verifier/ruleset/current.json",
        ruleset_public_key_path="/etc/traincapsule-verifier/ruleset-public-key.pem",
    )


def test_read_only_producer_promoter_and_updater_material_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Anchor")
    _git(source, "config", "user.email", "anchor@example.invalid")
    (source / "value.txt").write_text("base\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "base")
    base = _git(source, "rev-parse", "HEAD")
    (source / "value.txt").write_text("merged\n", encoding="utf-8")
    _git(source, "commit", "-am", "merged")
    merged = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")
    transaction_root = tmp_path / "transactions"
    transaction_root.mkdir(mode=0o700)
    transaction = {
        "schemaVersion": "3.1",
        "transactionId": "PRPUB-V3_PRODUCT_001-" + merged[:12].upper(),
        "phase": "MERGED",
        "baseSha": base,
        "candidateSha": merged,
        "mergedMainSha": merged,
        "pullRequestNumber": 41,
        "updatedAt": NOW.isoformat().replace("+00:00", "Z"),
    }
    transaction_path = transaction_root / f"{merged}.json"
    transaction_path.write_text(
        __import__("json").dumps(transaction, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    transaction_path.chmod(0o600)
    inbox = tmp_path / "inbox"
    outbox = tmp_path / "outbox"
    promoted = tmp_path / "promoted"
    inbox.mkdir(mode=0o700)
    outbox.mkdir(mode=0o700)
    promoted.mkdir(mode=0o700)
    identity = pwd.getpwuid(os.getuid())

    def service_identity(_name: str) -> SimpleNamespace:
        return SimpleNamespace(pw_uid=identity.pw_uid, pw_gid=identity.pw_gid)

    monkeypatch.setattr(
        producer.pwd,
        "getpwnam",
        service_identity,
    )
    monkeypatch.setattr(producer.os, "geteuid", lambda: 0)
    policy = _policy()
    jobs = producer.stage_jobs(
        policy, transaction_root=transaction_root, inbox=inbox, now=NOW
    )
    assert len(jobs) == 1
    assert producer.stage_jobs(
        policy,
        transaction_root=transaction_root,
        inbox=inbox,
        now=NOW + timedelta(minutes=1),
    ) == []
    assert producer.stage_jobs(
        policy,
        transaction_root=transaction_root,
        inbox=inbox,
        now=NOW + timedelta(minutes=31),
    ) == []

    ruleset_key = Ed25519PrivateKey.generate()
    ruleset_core = {
        "repository": policy.repository,
        "baseBranch": "main",
        "rulesetId": 1,
        "enforcement": "active",
        "requiredCheckAppIds": policy.required_check_app_ids,
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": True,
        "directBranchUpdatesForbidden": True,
        "autoMergeEnabled": True,
    }
    ruleset_digest = sha256_digest(canonical_json_bytes(ruleset_core))
    ruleset_provisional = RulesetObservationReceipt(
        schema_version="3.1",
        observation_id=ruleset_observation_identifier(ruleset_digest, NOW),
        observation_digest=ruleset_digest,
        repository=policy.repository,
        base_branch="main",
        ruleset_id=1,
        enforcement="active",
        required_check_app_ids=policy.required_check_app_ids,
        bypass_actor_count=0,
        deletion_forbidden=True,
        force_push_forbidden=True,
        pull_request_required=True,
        direct_branch_updates_forbidden=True,
        auto_merge_enabled=True,
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        issuer_id="RULESET:OBSERVER",
        issuer_key_id="KEY:RULESET:ACTIVE",
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    ruleset = ruleset_provisional.model_copy(
        update={"signature": sign_model(ruleset_provisional, ruleset_key)}
    )
    observer_key = Ed25519PrivateKey.generate()
    original_trusted = producer._trusted_raw  # pyright: ignore[reportPrivateUsage]
    fixed = {
        policy.private_key_path: b"unused-app-key",
        policy.observer_key_path: _private_raw(observer_key),
        policy.ruleset_receipt_path: canonical_json_bytes(ruleset),
        policy.ruleset_public_key_path: _public_raw(ruleset_key),
    }

    def trusted(path: Path, *, uid: int, mode: int, maximum: int) -> bytes:
        if str(path) in fixed:
            return fixed[str(path)]
        return original_trusted(path, uid=os.getuid(), mode=mode, maximum=maximum)

    monkeypatch.setattr(producer, "_trusted_raw", trusted)
    monkeypatch.setattr(producer.os, "geteuid", lambda: identity.pw_uid)

    def github_json(path: str, _token: str) -> object:
        if path.endswith("/branches/main"):
            return {"commit": {"sha": merged}}
        if path.endswith("/pulls/41"):
            return {
                "merged": True,
                "merge_commit_sha": merged,
                "head": {"sha": merged},
                "base": {"ref": "main", "sha": base},
            }
        return {
            "check_runs": [
                {
                    "id": 1,
                    "name": "TrainCapsule / Factory quality",
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 15368},
                },
                {
                    "id": 2,
                    "name": "TrainCapsule / Machine policy",
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 900002},
                },
            ]
        }

    monkeypatch.setattr(producer, "_github_json", github_json)
    original_git = producer._run_git  # pyright: ignore[reportPrivateUsage]

    def local_git(arguments: list[str], *, cwd: Path, token: str | None = None) -> str:
        rewritten = [
            str(source) if value.startswith("https://github.com/") else value
            for value in arguments
        ]
        return original_git(rewritten, cwd=cwd, token=None)

    monkeypatch.setattr(producer, "_run_git", local_git)
    outputs = producer.produce(
        policy,
        inbox=inbox,
        outbox=outbox,
        token_factory=lambda _policy, _key: "ghs_local_test_token",
        now=NOW + timedelta(minutes=1),
    )
    assert len(outputs) == 5
    assert producer.produce(
        policy,
        inbox=inbox,
        outbox=outbox,
        token_factory=lambda _policy, _key: "ghs_local_test_token",
        now=NOW + timedelta(minutes=2),
    ) == outputs

    observer_public = tmp_path / "observer-public.pem"
    observer_public.write_bytes(_public_raw(observer_key))
    observer_public.chmod(0o444)
    monkeypatch.setattr(producer.os, "geteuid", lambda: 0)

    def no_chown(
        _path: str | Path,
        _uid: int,
        _gid: int,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del dir_fd, follow_symlinks

    monkeypatch.setattr(producer.os, "chown", no_chown)
    promoted_files = producer.promote(
        outbox=outbox,
        updater_inbox=promoted,
        observer_public_key_path=observer_public,
    )
    assert len(promoted_files) == 5
    assert producer.promote(
        outbox=outbox,
        updater_inbox=promoted,
        observer_public_key_path=observer_public,
    ) == []
    request_path = next(promoted.glob("*.request.json"))
    request = producer.AnchorUpdateRequest.model_validate_json(
        request_path.read_bytes(), strict=True
    )
    assert request.base_sha == base
    assert request.merged_main_sha == merged
    assert request.merged_main_tree_sha == tree
    assert request.bundle_digest == sha256_digest(next(promoted.glob("*.bundle")).read_bytes())
    anchor = tmp_path / "anchor.git"
    _git(tmp_path, "clone", "--bare", str(source), str(anchor))
    _git(anchor, "remote", "remove", "origin")
    _git(anchor, "update-ref", "refs/heads/main", base)
    shutil.rmtree(anchor / "hooks")
    target_stem = request_path.name.removesuffix(".request.json")
    journal = advance_anchor(
        request_raw=request_path.read_bytes(),
        observed_main_raw=(promoted / f"{target_stem}.observed.json").read_bytes(),
        ruleset_raw=(promoted / f"{target_stem}.ruleset.json").read_bytes(),
        publication_transaction_raw=(
            promoted / f"{target_stem}.publication.json"
        ).read_bytes(),
        bundle_path=promoted / f"{target_stem}.bundle",
        policy=AnchorUpdatePolicy(
            repository=policy.repository,
            source_generation_id=policy.source_generation_id,
            source_generation_digest=policy.source_generation_digest,
            anchor_root="/var/lib/traincapsule-runtime/git",
            transaction_root="/var/lib/traincapsule-verifier/anchor-update-journal",
        ),
        selector_public_key_raw=_public_raw(observer_key),
        ruleset_public_key_raw=_public_raw(ruleset_key),
        now=NOW + timedelta(minutes=2),
        anchor_root=anchor,
        transaction_root=tmp_path / "update-journal",
    )
    assert journal.phase == "COMMITTED"
    assert _git(anchor, "rev-parse", "main") == merged


def test_producer_policy_rejects_write_scope_and_pat_style_shortcut() -> None:
    policy = _policy().model_dump(mode="python")
    policy["permissions"] = {"contents": "write"}
    with pytest.raises(ValueError):
        AnchorProducerPolicy.model_validate(policy)
    assert "PAT" not in canonical_json_bytes(_policy()).decode()
