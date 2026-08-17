from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from traincapsule_verifier.canonical import canonical_json_bytes, model_digest, sha256_digest
from traincapsule_verifier.crypto import sign_model
from traincapsule_verifier.git_anchor_updater import (
    AnchorUpdatePolicy,
    AnchorUpdateRequest,
    advance_anchor,
    valid_main_parent_binding,
)
from traincapsule_verifier.models import (
    ObservedMainReceipt,
    RulesetObservationReceipt,
    ruleset_observation_identifier,
)

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def test_parent_binding_accepts_only_exact_protected_merge_shapes() -> None:
    base = "a" * 40
    candidate = "b" * 40
    assert valid_main_parent_binding([base], base_sha=base, candidate_sha=candidate)
    assert valid_main_parent_binding(
        [base, candidate], base_sha=base, candidate_sha=candidate
    )
    assert not valid_main_parent_binding(
        [candidate, base], base_sha=base, candidate_sha=candidate
    )
    assert not valid_main_parent_binding(
        [base, "c" * 40], base_sha=base, candidate_sha=candidate
    )
    assert not valid_main_parent_binding(
        [base, candidate, "c" * 40], base_sha=base, candidate_sha=candidate
    )


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def _public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _fixture(tmp_path: Path, *, lagged: bool = False) -> dict[str, object]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Anchor Test")
    _git(source, "config", "user.email", "anchor@example.invalid")
    (source / "value.txt").write_text("base\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "base")
    anchor_base = _git(source, "rev-parse", "HEAD")
    anchor = tmp_path / "anchor.git"
    _git(tmp_path, "clone", "--bare", str(source), str(anchor))
    _git(anchor, "remote", "remove", "origin")
    if lagged:
        (source / "intermediate.txt").write_text("protected predecessor\n", encoding="utf-8")
        _git(source, "add", "intermediate.txt")
        _git(source, "commit", "-m", "protected predecessor")
    base = _git(source, "rev-parse", "HEAD")
    __import__("shutil").rmtree(anchor / "hooks")
    (source / "value.txt").write_text("merged\n", encoding="utf-8")
    _git(source, "commit", "-am", "merged")
    merged = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")
    bundle = tmp_path / "main.bundle"
    _git(source, "bundle", "create", str(bundle), "main")
    selector = Ed25519PrivateKey.generate()
    ruleset_key = Ed25519PrivateKey.generate()
    core: dict[str, object] = {
        "repository": "TasfiqJ/TrainCapsule",
        "baseBranch": "main",
        "rulesetId": 1,
        "enforcement": "active",
        "requiredCheckAppIds": {},
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": False,
        "directBranchUpdatesForbidden": False,
        "autoMergeEnabled": False,
    }
    ruleset_digest = sha256_digest(canonical_json_bytes(core))
    ruleset_provisional = RulesetObservationReceipt(
        schema_version="3.1",
        observation_id=ruleset_observation_identifier(ruleset_digest, NOW),
        observation_digest=ruleset_digest,
        repository="TasfiqJ/TrainCapsule",
        base_branch="main",
        ruleset_id=1,
        enforcement="active",
        required_check_app_ids={},
        bypass_actor_count=0,
        deletion_forbidden=True,
        force_push_forbidden=True,
        pull_request_required=False,
        direct_branch_updates_forbidden=False,
        auto_merge_enabled=False,
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
    observed_provisional = ObservedMainReceipt(
        schema_version="3.1",
        observation_id="OBS:ANCHOR_TEST_0001",
        repository="TasfiqJ/TrainCapsule",
        verified_main_sha=merged,
        verified_main_tree_sha=tree,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "a" * 64,
        ruleset_observation_digest=model_digest(ruleset),
        required_check_digests={"FACTORY_QUALITY": "sha256:" + "b" * 64},
        github_app_id=900001,
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        issuer_id="SELECTOR:EXACT-MAIN",
        issuer_key_id="KEY:SELECTOR:ACTIVE",
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    observed = observed_provisional.model_copy(
        update={"signature": sign_model(observed_provisional, selector)}
    )
    publication_raw = canonical_json_bytes(
        {
            "phase": "MERGED",
            "baseSha": base,
            "candidateSha": merged,
            "mergedMainSha": merged,
        }
    )
    request = AnchorUpdateRequest(
        request_id="ANCHOR:TEST_0001",
        repository="TasfiqJ/TrainCapsule",
        base_sha=base,
        merged_main_sha=merged,
        merged_main_tree_sha=tree,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "a" * 64,
        observed_main_digest=model_digest(observed),
        ruleset_observation_digest=model_digest(ruleset),
        publication_transaction_digest=sha256_digest(publication_raw),
        bundle_digest=sha256_digest(bundle.read_bytes()),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    policy = AnchorUpdatePolicy(
        repository="TasfiqJ/TrainCapsule",
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "a" * 64,
        anchor_root="/var/lib/traincapsule-runtime/git",
        transaction_root="/var/lib/traincapsule-verifier/anchor-update-journal",
    )
    return {
        "source": source,
        "base": base,
        "anchor_base": anchor_base,
        "anchor": anchor,
        "merged": merged,
        "bundle": bundle,
        "selector": selector,
        "ruleset_key": ruleset_key,
        "ruleset": ruleset,
        "observed": observed,
        "publication_raw": publication_raw,
        "request": request,
        "policy": policy,
    }


def _advance(
    values: dict[str, object],
    tmp_path: Path,
    *,
    failpoint: Callable[[str], None] | None = None,
):  # type: ignore[no-untyped-def]
    return advance_anchor(
        request_raw=canonical_json_bytes(values["request"]),  # type: ignore[arg-type]
        observed_main_raw=canonical_json_bytes(values["observed"]),  # type: ignore[arg-type]
        ruleset_raw=canonical_json_bytes(values["ruleset"]),  # type: ignore[arg-type]
        publication_transaction_raw=values["publication_raw"],  # type: ignore[arg-type]
        bundle_path=values["bundle"],  # type: ignore[arg-type]
        policy=values["policy"],  # type: ignore[arg-type]
        selector_public_key_raw=_public(values["selector"]),  # type: ignore[arg-type]
        ruleset_public_key_raw=_public(values["ruleset_key"]),  # type: ignore[arg-type]
        now=NOW + timedelta(minutes=1),
        anchor_root=values["anchor"],  # type: ignore[arg-type]
        transaction_root=tmp_path / "journal",
        failpoint=failpoint,
    )


def test_anchor_update_is_exact_atomic_and_idempotent(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    first = _advance(values, tmp_path)
    second = _advance(values, tmp_path)
    assert first.phase == second.phase == "COMMITTED"
    assert _git(values["anchor"], "rev-parse", "main") == values["merged"]  # type: ignore[arg-type]
    assert _git(values["anchor"], "remote") == ""  # type: ignore[arg-type]


def test_anchor_update_catches_up_only_through_ancestral_protected_base(
    tmp_path: Path,
) -> None:
    values = _fixture(tmp_path, lagged=True)
    assert values["anchor_base"] != values["base"]
    journal = _advance(values, tmp_path)
    assert journal.phase == "COMMITTED"
    assert _git(values["anchor"], "rev-parse", "main") == values["merged"]  # type: ignore[arg-type]


def test_anchor_update_rejects_nonancestral_local_anchor(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    _git(unrelated, "init", "-b", "main")
    _git(unrelated, "config", "user.name", "Unrelated")
    _git(unrelated, "config", "user.email", "unrelated@example.invalid")
    (unrelated / "other.txt").write_text("unrelated\n", encoding="utf-8")
    _git(unrelated, "add", ".")
    _git(unrelated, "commit", "-m", "unrelated")
    unrelated_sha = _git(unrelated, "rev-parse", "HEAD")
    anchor = values["anchor"]
    _git(anchor, "fetch", "--no-tags", str(unrelated), "refs/heads/main")  # type: ignore[arg-type]
    _git(anchor, "update-ref", "refs/heads/main", unrelated_sha)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not an ancestor"):
        _advance(values, tmp_path)


@pytest.mark.parametrize("phase", ["PREPARED", "OBJECTS_IMPORTED", "REF_ADVANCED"])
def test_anchor_update_recovers_every_durable_crash_window(
    tmp_path: Path, phase: str
) -> None:
    values = _fixture(tmp_path)

    def crash(observed: str) -> None:
        if observed == phase:
            raise RuntimeError(f"crash after {phase}")

    with pytest.raises(RuntimeError, match="crash after"):
        _advance(values, tmp_path, failpoint=crash)
    recovered = _advance(values, tmp_path)
    assert recovered.phase == "COMMITTED"
    assert _git(values["anchor"], "rev-parse", "main") == values["merged"]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "attack",
    ["stale", "wrong-parent", "extra-ref", "substitution", "hard-link"],
)
def test_anchor_update_rejects_hostile_evidence(tmp_path: Path, attack: str) -> None:
    values = _fixture(tmp_path)
    if attack == "stale":
        values["request"] = values["request"].model_copy(  # type: ignore[union-attr]
            update={"expires_at": NOW + timedelta(seconds=1)}
        )
    elif attack == "wrong-parent":
        values["request"] = values["request"].model_copy(  # type: ignore[union-attr]
            update={"base_sha": "c" * 40}
        )
    elif attack == "extra-ref":
        source = values["source"]
        _git(source, "branch", "extra")  # type: ignore[arg-type]
        _git(source, "bundle", "create", str(values["bundle"]), "--all")  # type: ignore[arg-type]
        values["request"] = values["request"].model_copy(  # type: ignore[union-attr]
            update={"bundle_digest": sha256_digest(values["bundle"].read_bytes())}  # type: ignore[union-attr]
        )
    elif attack == "substitution":
        values["bundle"].write_bytes(values["bundle"].read_bytes() + b"tamper")  # type: ignore[union-attr]
    else:
        linked = tmp_path / "linked.bundle"
        linked.hardlink_to(values["bundle"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _advance(values, tmp_path)
    assert _git(values["anchor"], "rev-parse", "main") == values["base"]  # type: ignore[arg-type]
