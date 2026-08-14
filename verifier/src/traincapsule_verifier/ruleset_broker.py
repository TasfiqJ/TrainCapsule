"""Root-only promotion of independently signed ruleset observations."""

from __future__ import annotations

import fcntl
import os
import pwd
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical import canonical_json_bytes
from .filesystem import (
    TrustedPathError,
    TrustedRoot,
    atomic_write_new,
    open_trusted_root,
    read_bounded_file,
)
from .models import RulesetObservationReceipt
from .public_crypto import SignatureError, load_public_key, verify_model_signature

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")


def promote_ruleset_observation(
    raw: bytes, *, target: TrustedRoot, public_key: Ed25519PublicKey
) -> None:
    receipt = RulesetObservationReceipt.model_validate_json(raw, strict=True)
    if canonical_json_bytes(receipt) != raw:
        raise ValueError("ruleset observation is not canonical")
    verify_model_signature(receipt, public_key)
    now = datetime.now(UTC)
    if receipt.observed_at > now or receipt.expires_at <= now:
        raise ValueError("ruleset observation is stale")
    descriptor = target.descriptor
    target_owner = os.fstat(descriptor).st_uid
    version_name = f"{receipt.observation_id}.json"
    try:
        atomic_write_new(
            target,
            version_name,
            raw,
            mode=0o644,
            owner_uid=target_owner,
            owner_gid=os.fstat(descriptor).st_gid,
        )
    except TrustedPathError:
        if read_bounded_file(target, version_name) != raw:
            raise ValueError("ruleset observation identity conflicts") from None
    current: RulesetObservationReceipt | None = None
    try:
        current_raw = read_bounded_file(target, "current.json")
        current = RulesetObservationReceipt.model_validate_json(current_raw, strict=True)
        verify_model_signature(current, public_key)
    except FileNotFoundError:
        pass
    if current is not None:
        if current.observation_id == receipt.observation_id:
            if canonical_json_bytes(current) != raw:
                raise ValueError("current ruleset selector conflicts")
            return
        if current.observed_at >= receipt.observed_at:
            raise ValueError("ruleset observation does not advance the selector")
    pending = f".{receipt.observation_id}.current.pending"
    try:
        atomic_write_new(
            target,
            pending,
            raw,
            mode=0o444,
            owner_uid=target_owner,
            owner_gid=os.fstat(descriptor).st_gid,
        )
    except TrustedPathError:
        if read_bounded_file(target, pending) != raw:
            raise ValueError("ruleset promotion recovery bytes conflict") from None
    os.rename(pending, "current.json", src_dir_fd=descriptor, dst_dir_fd=descriptor)
    os.fsync(descriptor)


def promote_ruleset_outbox_item(
    name: str,
    raw: bytes,
    *,
    target: TrustedRoot,
    public_key: Ed25519PublicKey,
) -> None:
    """Skip an exact immutable history item; promote only unseen observations."""
    try:
        existing = read_bounded_file(target, name, maximum_bytes=1_000_000)
    except FileNotFoundError:
        receipt = RulesetObservationReceipt.model_validate_json(raw, strict=True)
        if canonical_json_bytes(receipt) != raw:
            raise ValueError("ruleset observation is not canonical") from None
        verify_model_signature(receipt, public_key)
        try:
            current = RulesetObservationReceipt.model_validate_json(
                read_bounded_file(target, "current.json"), strict=True
            )
        except FileNotFoundError:
            current = None
        if current is not None:
            verify_model_signature(current, public_key)
            if current.observed_at >= receipt.observed_at:
                return
        promote_ruleset_observation(raw, target=target, public_key=public_key)
        return
    if existing != raw:
        raise ValueError("ruleset observation history conflicts")


def main() -> int:
    if sys.argv[1:] != ["process-outbox"]:
        print("usage: traincapsule-verifier-ruleset-broker process-outbox", file=sys.stderr)
        return 2
    try:
        if os.geteuid() != 0:
            raise ValueError("ruleset broker requires root")
        observer_uid = pwd.getpwnam("traincapsule-ruleset-observer").pw_uid
        with (
            open_trusted_root(CONFIG, expected_uid=0) as config,
            open_trusted_root(ROOT / "ruleset-outbox", expected_uid=observer_uid) as source,
            open_trusted_root(ROOT / "ruleset", expected_uid=0) as target,
        ):
            public_key = load_public_key(
                read_bounded_file(config, "ruleset-public-key.pem")
            )
            fcntl.flock(target.descriptor, fcntl.LOCK_EX)
            for name in sorted(os.listdir(source.descriptor)):
                if not name.startswith("RULESET:") or not name.endswith(".json"):
                    continue
                promote_ruleset_outbox_item(
                    name,
                    read_bounded_file(source, name, maximum_bytes=1_000_000),
                    target=target,
                    public_key=public_key,
                )
        return 0
    except (KeyError, OSError, SignatureError, TrustedPathError, ValueError):
        print("ruleset observation broker rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
