from __future__ import annotations

import os
import pwd
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from traincapsule_verifier import ruleset_observer
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.crypto import sign_model
from traincapsule_verifier.filesystem import open_trusted_root
from traincapsule_verifier.models import (
    ObservedMainReceipt,
    RulesetObservationReceipt,
    ruleset_observation_identifier,
)
from traincapsule_verifier.observed_main_selector import verified_check_digests
from traincapsule_verifier.ruleset_broker import (
    promote_ruleset_observation,
    promote_ruleset_outbox_item,
)


def test_ruleset_observer_accepts_github_null_as_no_bypass_and_uses_graphql_auto_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ruleset_observer.has_no_bypass_actors(None)
    assert ruleset_observer.has_no_bypass_actors([])
    assert not ruleset_observer.has_no_bypass_actors([{"actor_id": 1}])

    def fake_graphql(
        _query: str, variables: dict[str, str], _token: str
    ) -> object:
        return {
            "data": {
                "repository": {
                    "autoMergeAllowed": variables
                    == {"owner": "TasfiqJ", "name": "TrainCapsule"}
                }
            }
        }

    monkeypatch.setattr(
        ruleset_observer,
        "_graphql",
        fake_graphql,
    )
    assert ruleset_observer.repository_auto_merge_enabled(
        "TasfiqJ/TrainCapsule", "installation-token"
    )


def _ruleset_receipt(
    key: Ed25519PrivateKey, observed_at: datetime
) -> RulesetObservationReceipt:
    core = {
        "repository": "TasfiqJ/TrainCapsule",
        "baseBranch": "main",
        "rulesetId": 20_794_549,
        "enforcement": "active",
        "requiredCheckAppIds": {"Factory quality": 15368},
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": True,
        "directBranchUpdatesForbidden": True,
        "autoMergeEnabled": True,
    }
    digest = sha256_digest(canonical_json_bytes(core))
    provisional = RulesetObservationReceipt(
        schema_version="3.1",
        observation_id=ruleset_observation_identifier(digest, observed_at),
        observation_digest=digest,
        repository="TasfiqJ/TrainCapsule",
        base_branch="main",
        ruleset_id=20_794_549,
        enforcement="active",
        required_check_app_ids={"Factory quality": 15368},
        bypass_actor_count=0,
        deletion_forbidden=True,
        force_push_forbidden=True,
        pull_request_required=True,
        direct_branch_updates_forbidden=True,
        auto_merge_enabled=True,
        observed_at=observed_at,
        expires_at=observed_at + timedelta(minutes=15),
        issuer_id="RULESET:OBSERVER",
        issuer_key_id="KEY:RULESET:ACTIVE",
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    return provisional.model_copy(update={"signature": sign_model(provisional, key)})


def test_selector_accepts_heterogeneous_trusted_app_mapping_only() -> None:
    required = {"Factory quality": 15368, "TrainCapsule / Machine policy": 900001}
    runs: list[object] = [
        {"id": 1, "name": "Factory quality", "conclusion": "success", "app": {"id": 15368}},
        {
            "id": 2,
            "name": "TrainCapsule / Machine policy",
            "conclusion": "success",
            "app": {"id": 900001},
        },
    ]
    assert set(verified_check_digests(runs, required)) == set(required)
    forged: list[object] = [
        runs[0],
        {
            "id": 2,
            "name": "TrainCapsule / Machine policy",
            "conclusion": "success",
            "app": {"id": 15368},
        },
    ]
    with pytest.raises(ValueError, match="missing or spoofed"):
        verified_check_digests(forged, required)


def test_observed_main_receipt_accepts_exact_github_check_names() -> None:
    observed = ObservedMainReceipt(
        schema_version="3.1",
        observation_id="OBS:CHECK_NAMES_0001",
        repository="TasfiqJ/TrainCapsule",
        verified_main_sha="a" * 40,
        verified_main_tree_sha="b" * 40,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "c" * 64,
        ruleset_observation_digest="sha256:" + "d" * 64,
        required_check_digests={
            "TrainCapsule / Factory quality": "sha256:" + "e" * 64,
            "TrainCapsule / Machine policy": "sha256:" + "f" * 64,
        },
        github_app_id=4_580_794,
        observed_at=datetime(2026, 8, 13, 21, 0, tzinfo=UTC),
        expires_at=datetime(2026, 8, 13, 21, 15, tzinfo=UTC),
        issuer_id="SELECTOR:EXACT-MAIN",
        issuer_key_id="KEY:SELECTOR:ACTIVE",
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    assert set(observed.required_check_digests) == {
        "TrainCapsule / Factory quality",
        "TrainCapsule / Machine policy",
    }
    payload = observed.model_dump(mode="python", by_alias=False)
    payload["required_check_digests"] = {
        "TrainCapsule / Security\n": "sha256:" + "a" * 64
    }
    with pytest.raises(ValueError, match="check name"):
        ObservedMainReceipt.model_validate(payload)


def test_selector_reads_request_through_retained_directory_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import traincapsule_verifier.observed_main_selector as selector

    request_root = tmp_path / "activation-requests"
    request_root.mkdir(mode=0o700)
    original = b'{"trusted":"original"}'
    (request_root / "ACT:REQUEST.json").write_bytes(original)
    captured: list[bytes] = []
    real_read = selector.read_bounded_file
    swapped = False

    def swap_after_descriptor_read(root: object, name: str, **kwargs: object) -> bytes:
        nonlocal swapped
        raw = real_read(root, name, **kwargs)  # type: ignore[arg-type]
        if not swapped:
            swapped = True
            request_root.rename(tmp_path / "original-root")
            request_root.mkdir(mode=0o700)
            (request_root / name).write_bytes(b'{"forged":"replacement"}')
        return raw

    account = pwd.struct_passwd(
        ("traincapsule-selector", "x", os.getuid(), os.getgid(), "", "/", "/bin/false")
    )

    def get_account(_name: str) -> pwd.struct_passwd:
        return account

    def capture(raw: bytes, *, selector_uid: int) -> None:
        assert selector_uid == os.getuid()
        captured.append(raw)

    monkeypatch.setattr(selector, "REQUEST_ROOT", request_root)
    monkeypatch.setattr(selector.pwd, "getpwnam", get_account)
    monkeypatch.setattr(selector.os, "geteuid", os.getuid)
    monkeypatch.setattr(selector.sys, "argv", ["selector", "process-requests"])
    monkeypatch.setattr(selector, "read_bounded_file", swap_after_descriptor_read)
    monkeypatch.setattr(selector, "_select", capture)
    assert selector.main() == 0
    assert captured == [original]


def test_selector_stale_request_does_not_starve_current_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import traincapsule_verifier.observed_main_selector as selector

    request_root = tmp_path / "activation-requests"
    request_root.mkdir(mode=0o700)
    (request_root / "ACT:000.json").write_bytes(b"stale")
    (request_root / "ACT:999.json").write_bytes(b"current")
    selected: list[bytes] = []
    account = pwd.struct_passwd(
        ("traincapsule-selector", "x", os.getuid(), os.getgid(), "", "/", "/bin/false")
    )

    def select(raw: bytes, *, selector_uid: int) -> None:
        assert selector_uid == os.getuid()
        if raw == b"stale":
            raise ValueError("stale SHA")
        selected.append(raw)

    def get_account(_name: str) -> pwd.struct_passwd:
        return account

    monkeypatch.setattr(selector, "REQUEST_ROOT", request_root)
    monkeypatch.setattr(selector.pwd, "getpwnam", get_account)
    monkeypatch.setattr(selector.os, "geteuid", os.getuid)
    monkeypatch.setattr(selector.sys, "argv", ["selector", "process-requests"])
    monkeypatch.setattr(selector, "_select", select)

    assert selector.main() == 0
    assert selected == [b"current"]


def test_ruleset_broker_rotates_replays_and_recovers_after_preselector_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import traincapsule_verifier.ruleset_broker as broker

    target_path = tmp_path / "ruleset"
    target_path.mkdir(mode=0o700)
    key = Ed25519PrivateKey.generate()
    first = _ruleset_receipt(key, datetime.now(UTC) - timedelta(minutes=2))
    second = _ruleset_receipt(key, datetime.now(UTC) - timedelta(minutes=1))
    with open_trusted_root(target_path, expected_uid=os.getuid()) as target:
        promote_ruleset_observation(
            canonical_json_bytes(first), target=target, public_key=key.public_key()
        )
        promote_ruleset_observation(
            canonical_json_bytes(first), target=target, public_key=key.public_key()
        )
        original_rename = broker.os.rename

        def crash(*args: object, **kwargs: object) -> None:
            raise OSError("simulated pre-selector crash")

        monkeypatch.setattr(broker.os, "rename", crash)
        with pytest.raises(OSError, match="simulated"):
            promote_ruleset_observation(
                canonical_json_bytes(second), target=target, public_key=key.public_key()
            )
        monkeypatch.setattr(broker.os, "rename", original_rename)
        promote_ruleset_observation(
            canonical_json_bytes(second), target=target, public_key=key.public_key()
        )
    assert RulesetObservationReceipt.model_validate_json(
        (target_path / "current.json").read_bytes(), strict=True
    ).observation_id == second.observation_id
    assert (target_path / f"{first.observation_id}.json").exists()
    assert (target_path / f"{second.observation_id}.json").exists()
    assert (target_path / "current.json").stat().st_mode & 0o777 == 0o644
    assert (target_path / f"{first.observation_id}.json").stat().st_mode & 0o777 == 0o644
    assert (target_path / f"{second.observation_id}.json").stat().st_mode & 0o777 == 0o644


def test_ruleset_broker_rejects_mismatched_signature(tmp_path: Path) -> None:
    target_path = tmp_path / "ruleset"
    target_path.mkdir(mode=0o700)
    receipt = _ruleset_receipt(
        Ed25519PrivateKey.generate(), datetime.now(UTC) - timedelta(minutes=1)
    )
    with (
        open_trusted_root(target_path, expected_uid=os.getuid()) as target,
        pytest.raises(ValueError, match="signature"),
    ):
        promote_ruleset_observation(
            canonical_json_bytes(receipt),
            target=target,
            public_key=Ed25519PrivateKey.generate().public_key(),
        )


def test_ruleset_broker_skips_exact_expired_history_but_rejects_conflicts(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "ruleset"
    target_path.mkdir(mode=0o700)
    key = Ed25519PrivateKey.generate()
    expired = _ruleset_receipt(key, datetime.now(UTC) - timedelta(hours=1))
    raw = canonical_json_bytes(expired)
    name = f"{expired.observation_id}.json"
    (target_path / name).write_bytes(raw)

    with open_trusted_root(target_path, expected_uid=os.getuid()) as target:
        promote_ruleset_outbox_item(
            name, raw, target=target, public_key=key.public_key()
        )
        with pytest.raises(ValueError, match="history conflicts"):
            promote_ruleset_outbox_item(
                name, raw + b"\n", target=target, public_key=key.public_key()
            )


def test_ruleset_broker_verifies_then_skips_unpromoted_older_history(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "ruleset"
    target_path.mkdir(mode=0o700)
    key = Ed25519PrivateKey.generate()
    current = _ruleset_receipt(key, datetime.now(UTC) - timedelta(minutes=1))
    older = _ruleset_receipt(key, datetime.now(UTC) - timedelta(hours=1))
    older_raw = canonical_json_bytes(older)
    older_name = f"{older.observation_id}.json"

    with open_trusted_root(target_path, expected_uid=os.getuid()) as target:
        promote_ruleset_observation(
            canonical_json_bytes(current), target=target, public_key=key.public_key()
        )
        promote_ruleset_outbox_item(
            older_name, older_raw, target=target, public_key=key.public_key()
        )
        forged = older.model_copy(update={"signature": "B" * 88})
        with pytest.raises(ValueError, match="signature"):
            promote_ruleset_outbox_item(
                f"{older.observation_id}.forged.json",
                canonical_json_bytes(forged),
                target=target,
                public_key=key.public_key(),
            )

    assert not (target_path / older_name).exists()
    assert RulesetObservationReceipt.model_validate_json(
        (target_path / "current.json").read_bytes(), strict=True
    ).observation_id == current.observation_id
