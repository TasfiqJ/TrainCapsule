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
from traincapsule_verifier.models import RulesetObservationReceipt
from traincapsule_verifier.observed_main_selector import verified_check_digests
from traincapsule_verifier.ruleset_broker import promote_ruleset_observation


def test_ruleset_observer_accepts_github_null_as_no_bypass_and_uses_graphql_auto_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ruleset_observer._has_no_bypass_actors(None)
    assert ruleset_observer._has_no_bypass_actors([])
    assert not ruleset_observer._has_no_bypass_actors([{"actor_id": 1}])
    monkeypatch.setattr(
        ruleset_observer,
        "_graphql",
        lambda _query, variables, _token: {
            "data": {
                "repository": {
                    "autoMergeAllowed": variables
                    == {"owner": "TasfiqJ", "name": "TrainCapsule"}
                }
            }
        },
    )
    assert ruleset_observer._repository_auto_merge_enabled(
        "TasfiqJ/TrainCapsule", "installation-token"
    )


def _ruleset_receipt(
    key: Ed25519PrivateKey, observed_at: datetime
) -> RulesetObservationReceipt:
    core = {
        "repository": "TasfiqJ/TrainCapsule",
        "baseBranch": "main",
        "rulesetId": int(observed_at.timestamp()),
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
        observation_id=f"RULESET:{digest[7:39].upper()}",
        observation_digest=digest,
        repository="TasfiqJ/TrainCapsule",
        base_branch="main",
        ruleset_id=int(observed_at.timestamp()),
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
