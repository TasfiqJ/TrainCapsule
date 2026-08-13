"""Public-only verification boundary for controller callers.

This module deliberately has no issuer API and never imports private-key loading or
signing helpers.  Its only authority is root-owned public policy, public key,
revocation, anchor, and signed-receipt state.
"""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ValidationError

from .canonical import canonical_json_bytes, model_digest
from .filesystem import (
    TrustedPathError,
    TrustedRoot,
    assert_trusted_root,
    read_bounded_file,
    strict_json_loads,
)
from .models import (
    ActivationAuthorization,
    ActivationReceipt,
    AuthorityAnchor,
    CheckAuthorization,
    MachinePolicyReceipt,
    RevocationList,
    VerifierPolicy,
)
from .public_crypto import (
    SignatureError,
    load_public_key,
    public_key_fingerprint,
    verify_model_signature,
)

MAX_RECEIPT_BYTES = 5_000_000


class PublicVerificationError(RuntimeError):
    """A public authorization could not be established."""


def validate_root_owned_ancestry(path: Path) -> None:
    """Reject an active trust path whose existing ancestry is redirectable."""

    absolute = path.absolute()
    current = Path(absolute.anchor)
    root_observed = current.lstat()
    if (
        not stat.S_ISDIR(root_observed.st_mode)
        or root_observed.st_uid != 0
        or root_observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise PublicVerificationError("public trust-root ancestry is not root-controlled")
    for component in absolute.parts[1:-1]:
        current /= component
        observed = current.lstat()
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise PublicVerificationError("public trust-root ancestry is not a real directory")
        if observed.st_uid != 0 or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PublicVerificationError("public trust-root ancestry is not root-controlled")


def _load_model[T: BaseModel](root: TrustedRoot, relative: str, model: type[T]) -> T:
    raw = read_bounded_file(root, relative, maximum_bytes=MAX_RECEIPT_BYTES)
    strict_json_loads(raw)
    try:
        return model.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise PublicVerificationError(f"trusted {relative} contract is invalid") from exc


def read_untrusted_receipt(path: Path) -> bytes:
    """Read a caller-selected receipt without following links or accepting races."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PublicVerificationError("receipt cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PublicVerificationError("receipt must be a regular file")
        if before.st_size > MAX_RECEIPT_BYTES:
            raise PublicVerificationError("receipt exceeds size limit")
        chunks: list[bytes] = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(value) > MAX_RECEIPT_BYTES:
            raise PublicVerificationError("receipt exceeds size limit")
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise PublicVerificationError("receipt changed while being read")
        return value
    finally:
        os.close(descriptor)


class PublicVerifier:
    """Verifier containing public material only; it cannot mint any receipt."""

    def __init__(
        self,
        *,
        policy: VerifierPolicy,
        revocations: RevocationList,
        public_key: Ed25519PublicKey,
        anchor: AuthorityAnchor,
        receipt_root: TrustedRoot,
    ) -> None:
        self.policy = policy
        self.revocations = revocations
        self.public_key = public_key
        self.anchor = anchor
        self.receipt_root = receipt_root
        self._closed = False
        self._validate_authority()

    @classmethod
    def from_public_roots(
        cls,
        *,
        repository_root: Path,
        config_root: Path,
        state_root: Path,
        receipt_root: Path,
        expected_owner_uid: int = 0,
    ) -> PublicVerifier:
        """Open only public, controller-read-only roots outside the repository."""

        opened: list[TrustedRoot] = []
        verifier: PublicVerifier | None = None
        try:
            if expected_owner_uid == 0:
                for root_path in (config_root, state_root, receipt_root):
                    validate_root_owned_ancestry(root_path)
            config = assert_trusted_root(
                config_root, expected_uid=expected_owner_uid, repository_root=repository_root
            )
            opened.append(config)
            state = assert_trusted_root(
                state_root, expected_uid=expected_owner_uid, repository_root=repository_root
            )
            opened.append(state)
            receipts = assert_trusted_root(
                receipt_root, expected_uid=expected_owner_uid, repository_root=repository_root
            )
            opened.append(receipts)
            policy = _load_model(config, "policy.json", VerifierPolicy)
            revocations = _load_model(state, "revocations.json", RevocationList)
            anchor = _load_model(state, "authority-anchor.json", AuthorityAnchor)
            public_key = load_public_key(
                read_bounded_file(config, "public-key.pem", maximum_bytes=8192)
            )
            verifier = cls(
                policy=policy,
                revocations=revocations,
                public_key=public_key,
                anchor=anchor,
                receipt_root=receipts,
            )
            return verifier
        except (OSError, TrustedPathError, SignatureError) as exc:
            raise PublicVerificationError("public verifier trust state is unavailable") from exc
        finally:
            for root in reversed(opened):
                if verifier is None or root is not verifier.receipt_root:
                    root.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.receipt_root.close()

    def __enter__(self) -> PublicVerifier:
        if self._closed:
            raise PublicVerificationError("public verifier is closed")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _validate_authority(self) -> None:
        if public_key_fingerprint(self.public_key) != self.policy.public_key_fingerprint:
            raise PublicVerificationError("public key fingerprint does not match active policy")
        try:
            verify_model_signature(self.revocations, self.public_key)
        except SignatureError as exc:
            raise PublicVerificationError("revocation list signature is invalid") from exc
        exact = (
            (self.revocations.policy_id, self.policy.policy_id),
            (self.revocations.policy_version, self.policy.policy_version),
            (self.revocations.issuer_id, self.policy.issuer_id),
            (self.revocations.issuer_key_id, self.policy.issuer_key_id),
            (self.anchor.policy_id, self.policy.policy_id),
            (self.anchor.policy_version, self.policy.policy_version),
            (self.anchor.issuer_id, self.policy.issuer_id),
            (self.anchor.issuer_key_id, self.policy.issuer_key_id),
            (self.anchor.public_key_fingerprint, self.policy.public_key_fingerprint),
            (self.anchor.revocation_epoch, self.revocations.revocation_epoch),
            (self.anchor.revocation_list_digest, model_digest(self.revocations)),
            (self.anchor.previous_revocation_list_digest, self.revocations.previous_list_digest),
        )
        if any(observed != expected for observed, expected in exact):
            raise PublicVerificationError("authority state does not match external anchor")
        if self.revocations.revocation_epoch < self.policy.minimum_revocation_epoch:
            raise PublicVerificationError("revocation epoch is below policy minimum")

    def _validate_current_authority(self, now: datetime) -> None:
        if self._closed:
            raise PublicVerificationError("public verifier is closed")
        if self.revocations.issued_at.astimezone(UTC) > now + timedelta(minutes=5):
            raise PublicVerificationError("revocation list is future-dated")
        if self.revocations.expires_at.astimezone(UTC) <= now:
            raise PublicVerificationError("revocation list is expired")

    def _require_local_bytes(self, receipt_id: str, expected: bytes) -> None:
        try:
            observed = read_bounded_file(
                self.receipt_root, f"{receipt_id}.json", maximum_bytes=MAX_RECEIPT_BYTES
            )
        except (OSError, TrustedPathError) as exc:
            raise PublicVerificationError("matching authority receipt is unavailable") from exc
        if observed != expected:
            raise PublicVerificationError("authority receipt bytes differ from submitted receipt")

    def _reject_revoked(self, *, receipt_id: str, nonce: str, key_id: str, epoch: int) -> None:
        if epoch > self.revocations.revocation_epoch:
            raise PublicVerificationError("receipt revocation epoch is newer than trusted state")
        if (
            receipt_id in self.revocations.revoked_receipt_ids
            or nonce in self.revocations.revoked_nonces
            or key_id in self.revocations.revoked_key_ids
        ):
            raise PublicVerificationError("receipt is revoked")

    def verify_machine_receipt(
        self, receipt: MachinePolicyReceipt, *, now: datetime | None = None
    ) -> None:
        self.verify_machine_receipt_authority(receipt, now=now)
        self._require_local_bytes(receipt.receipt_id, canonical_json_bytes(receipt))

    def verify_machine_receipt_authority(
        self, receipt: MachinePolicyReceipt, *, now: datetime | None = None
    ) -> None:
        """Verify public authority without assuming the receipt is already promoted."""

        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        self._validate_current_authority(observed_now)
        try:
            verify_model_signature(receipt, self.public_key)
        except SignatureError as exc:
            raise PublicVerificationError("machine-policy receipt signature is invalid") from exc
        exact = (
            (receipt.policy_id, self.policy.policy_id),
            (receipt.policy_version, self.policy.policy_version),
            (receipt.issuer_id, self.policy.issuer_id),
            (receipt.issuer_key_id, self.policy.issuer_key_id),
            (receipt.source_generation_id, self.policy.active_source_generation_id),
            (receipt.source_generation_digest, self.policy.active_source_generation_digest),
        )
        if any(observed != expected for observed, expected in exact):
            raise PublicVerificationError("machine-policy receipt authority mismatch")
        if receipt.issued_at.astimezone(UTC) > observed_now + timedelta(minutes=5):
            raise PublicVerificationError("machine-policy receipt is future-dated")
        if receipt.expires_at.astimezone(UTC) <= observed_now:
            raise PublicVerificationError("machine-policy receipt is expired")
        self._reject_revoked(
            receipt_id=receipt.receipt_id,
            nonce=receipt.nonce,
            key_id=receipt.issuer_key_id,
            epoch=receipt.revocation_epoch,
        )

    def verify_activation_authority(
        self, receipt: ActivationReceipt, *, now: datetime | None = None
    ) -> None:
        """Verify activation authority before root-owned receipt promotion."""

        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        self._validate_current_authority(observed_now)
        try:
            verify_model_signature(receipt, self.public_key)
        except SignatureError as exc:
            raise PublicVerificationError("activation receipt signature is invalid") from exc
        if receipt.issued_at.astimezone(UTC) > observed_now + timedelta(minutes=5):
            raise PublicVerificationError("activation receipt is future-dated")
        if receipt.expires_at.astimezone(UTC) <= observed_now:
            raise PublicVerificationError("activation receipt is expired")
        self._reject_revoked(
            receipt_id=receipt.receipt_id,
            nonce=receipt.nonce,
            key_id=receipt.issuer_key_id,
            epoch=receipt.revocation_epoch,
        )
        expected = (
            (receipt.issuer_id, self.policy.issuer_id),
            (receipt.issuer_key_id, self.policy.issuer_key_id),
            (receipt.source_generation_id, self.policy.active_source_generation_id),
            (receipt.source_generation_digest, self.policy.active_source_generation_digest),
        )
        if any(observed != wanted for observed, wanted in expected):
            raise PublicVerificationError("activation receipt authority mismatch")
        linked = self.load_machine_receipt(receipt.machine_policy_receipt_id)
        self.verify_machine_receipt(linked, now=observed_now)
        if (
            receipt.machine_policy_receipt_digest != model_digest(linked)
            or linked.candidate_sha != receipt.verified_main_sha
        ):
            raise PublicVerificationError("activation linked machine-policy receipt mismatch")

    def load_machine_receipt(self, receipt_id: str) -> MachinePolicyReceipt:
        """Load a receipt by authority ID, never by a controller-selected path."""

        raw = read_bounded_file(
            self.receipt_root, f"{receipt_id}.json", maximum_bytes=MAX_RECEIPT_BYTES
        )
        strict_json_loads(raw)
        try:
            return MachinePolicyReceipt.model_validate_json(raw, strict=True)
        except (ValidationError, ValueError) as exc:
            raise PublicVerificationError("authority machine-policy receipt is invalid") from exc

    def authorize_receipt(
        self,
        receipt: MachinePolicyReceipt,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        base_sha: str,
        work_item_id: str,
        candidate_manifest_digest: str,
        now: datetime | None = None,
    ) -> CheckAuthorization:
        self.verify_machine_receipt(receipt, now=now)
        expected = (
            ("candidate SHA", receipt.candidate_sha, candidate_sha),
            ("candidate tree SHA", receipt.candidate_tree_sha, candidate_tree_sha),
            ("base SHA", receipt.base_sha, base_sha),
            ("work item", receipt.work_item_id, work_item_id),
            (
                "candidate manifest digest",
                receipt.candidate_manifest_digest,
                candidate_manifest_digest,
            ),
        )
        for label, observed, wanted in expected:
            if observed != wanted:
                raise PublicVerificationError(f"machine-policy receipt {label} mismatch")
        return CheckAuthorization(
            schema_version="3.1",
            check_name="TrainCapsule / Machine policy",
            candidate_sha=receipt.candidate_sha,
            conclusion="success",
            receipt_id=receipt.receipt_id,
            receipt_digest=model_digest(receipt),
        )

    def authorize_activation(
        self,
        receipt: ActivationReceipt,
        *,
        main_sha: str,
        source_generation_id: str,
        source_generation_digest: str,
        controller_binary_digest: str,
        controller_config_digest: str,
        now: datetime | None = None,
    ) -> ActivationAuthorization:
        self.verify_activation_authority(receipt, now=now)
        expected = (
            ("main SHA", receipt.verified_main_sha, main_sha),
            ("source generation", receipt.source_generation_id, source_generation_id),
            (
                "source generation digest",
                receipt.source_generation_digest,
                source_generation_digest,
            ),
            (
                "controller binary digest",
                receipt.controller_binary_digest,
                controller_binary_digest,
            ),
            (
                "controller config digest",
                receipt.controller_config_digest,
                controller_config_digest,
            ),
            ("issuer", receipt.issuer_id, self.policy.issuer_id),
            ("issuer key", receipt.issuer_key_id, self.policy.issuer_key_id),
            (
                "active source generation",
                source_generation_id,
                self.policy.active_source_generation_id,
            ),
            (
                "active source generation digest",
                source_generation_digest,
                self.policy.active_source_generation_digest,
            ),
        )
        for label, observed, wanted in expected:
            if observed != wanted:
                raise PublicVerificationError(f"activation receipt {label} mismatch")
        self._require_local_bytes(receipt.receipt_id, canonical_json_bytes(receipt))
        return ActivationAuthorization(
            schema_version="3.1",
            verified=True,
            verified_main_sha=receipt.verified_main_sha,
            activation_receipt_id=receipt.receipt_id,
            activation_receipt_digest=model_digest(receipt),
        )


def parse_receipt[T: BaseModel](path: Path, model: type[T]) -> T:
    raw = read_untrusted_receipt(path)
    strict_json_loads(raw)
    try:
        return model.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise PublicVerificationError("receipt contract is invalid") from exc
