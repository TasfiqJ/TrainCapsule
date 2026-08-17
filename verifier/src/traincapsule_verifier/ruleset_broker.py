"""Root-only promotion of independently signed ruleset observations."""

from __future__ import annotations

import fcntl
import os
import pwd
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, Field, ValidationError, model_validator

from .canonical import canonical_json_bytes
from .filesystem import (
    TrustedPathError,
    TrustedRoot,
    atomic_write_new,
    open_trusted_root,
    read_bounded_file,
)
from .models import Digest, Identifier, RulesetObservationReceipt, V31Model
from .public_crypto import SignatureError, load_public_key, verify_model_signature

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")


class LegacyRulesetObservationReceipt(V31Model):
    """Verified predecessor accepted only to advance the selector during migration."""

    observation_id: Identifier
    observation_digest: Digest
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_branch: Literal["main"]
    ruleset_id: int = Field(gt=0)
    enforcement: Literal["active"]
    required_check_app_ids: dict[str, int] = Field(min_length=1, max_length=64)
    bypass_actor_count: Literal[0]
    deletion_forbidden: Literal[True]
    force_push_forbidden: Literal[True]
    pull_request_required: Literal[True]
    direct_branch_updates_forbidden: Literal[True]
    auto_merge_enabled: Literal[True]
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    issuer_id: Identifier
    issuer_key_id: Identifier
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def validate_legacy_binding(self) -> LegacyRulesetObservationReceipt:
        from .canonical import sha256_digest

        lifetime = self.expires_at.astimezone(UTC) - self.observed_at.astimezone(UTC)
        if lifetime <= timedelta(0) or lifetime > timedelta(minutes=30):
            raise ValueError("legacy ruleset observation lifetime is invalid")
        core = {
            "repository": self.repository,
            "baseBranch": self.base_branch,
            "rulesetId": self.ruleset_id,
            "enforcement": self.enforcement,
            "requiredCheckAppIds": self.required_check_app_ids,
            "bypassActorCount": self.bypass_actor_count,
            "deletionForbidden": self.deletion_forbidden,
            "forcePushForbidden": self.force_push_forbidden,
            "pullRequestRequired": self.pull_request_required,
            "directBranchUpdatesForbidden": self.direct_branch_updates_forbidden,
            "autoMergeEnabled": self.auto_merge_enabled,
        }
        if self.observation_digest != sha256_digest(canonical_json_bytes(core)):
            raise ValueError("legacy ruleset observation digest is invalid")
        return self


def _verified_current(
    raw: bytes, public_key: Ed25519PublicKey
) -> RulesetObservationReceipt | LegacyRulesetObservationReceipt:
    try:
        receipt: RulesetObservationReceipt | LegacyRulesetObservationReceipt = (
            RulesetObservationReceipt.model_validate_json(raw, strict=True)
        )
    except ValidationError:
        receipt = LegacyRulesetObservationReceipt.model_validate_json(raw, strict=True)
    if canonical_json_bytes(receipt) != raw:
        raise ValueError("current ruleset selector is not canonical")
    verify_model_signature(receipt, public_key)
    return receipt


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
    current: RulesetObservationReceipt | LegacyRulesetObservationReceipt | None = None
    try:
        current_raw = read_bounded_file(target, "current.json")
        current = _verified_current(current_raw, public_key)
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
            current = _verified_current(
                read_bounded_file(target, "current.json"), public_key
            )
        except FileNotFoundError:
            current = None
        if current is not None and current.observed_at >= receipt.observed_at:
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
