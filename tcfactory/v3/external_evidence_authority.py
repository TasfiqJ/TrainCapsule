"""Privileged monotonic state for the V3 external-evidence authority.

The controller only reads the ledger.  A separately installed root broker uses
``ExternalEvidenceAuthorityBroker`` to provision genesis and rotate it under an
exclusive lock after independently verified authority files are staged.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import secrets
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class ExternalEvidenceAuthorityState(V3Model):
    state_version: int = Field(default=1, ge=1, le=1)
    authority_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    epoch: int = Field(ge=1)
    anchor_digest: Digest
    revocation_list_digest: Digest
    key_fingerprint: Digest
    previous_state_digest: Digest | None
    advanced_at: datetime

    @model_validator(mode="after")
    def validate_genesis(self) -> ExternalEvidenceAuthorityState:
        if (self.epoch == 1) != (self.previous_state_digest is None):
            raise ValueError("authority-state previous digest does not match its epoch")
        return self


class ExternalEvidenceAuthorityLedger(V3Model):
    ledger_version: int = Field(default=1, ge=1, le=1)
    entries: list[ExternalEvidenceAuthorityState] = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def validate_chain(self) -> ExternalEvidenceAuthorityLedger:
        for index, entry in enumerate(self.entries):
            expected_epoch = index + 1
            if entry.epoch != expected_epoch:
                raise ValueError("authority ledger epochs must be contiguous")
            expected_previous = (
                None
                if index == 0
                else "sha256:"
                + hashlib.sha256(self.entries[index - 1].canonical_json_bytes()).hexdigest()
            )
            if entry.previous_state_digest != expected_previous:
                raise ValueError("authority ledger digest chain is invalid")
        return self

    @property
    def current(self) -> ExternalEvidenceAuthorityState:
        return self.entries[-1]


class ExternalEvidenceAuthorityStateError(RuntimeError):
    """The independently protected authority state was absent or inconsistent."""


def key_fingerprint(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def load_external_evidence_authority_state(
    path: Path,
    *,
    expected_owner_uid: int = 0,
) -> ExternalEvidenceAuthorityLedger:
    """Read one root-owned, nonwritable, non-symlink monotonic ledger."""

    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise ExternalEvidenceAuthorityStateError(
            "external evidence monotonic authority ledger is unavailable"
        ) from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_owner_uid
            or metadata.st_mode & 0o022
            or metadata.st_size > 16_000_000
        ):
            raise ExternalEvidenceAuthorityStateError(
                "external evidence monotonic authority ledger is unsafe"
            )
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != metadata.st_size:
            raise ExternalEvidenceAuthorityStateError(
                "external evidence monotonic authority ledger changed while reading"
            )
    finally:
        os.close(fd)
    try:
        return ExternalEvidenceAuthorityLedger.model_validate_json(raw, strict=True)
    except ValueError as exc:
        raise ExternalEvidenceAuthorityStateError(
            "external evidence monotonic authority ledger is invalid"
        ) from exc


class ExternalEvidenceAuthorityBroker:
    """Minimal root broker providing atomic genesis/rotation and crash replay."""

    def __init__(self, ledger_path: Path, *, expected_owner_uid: int = 0) -> None:
        if not ledger_path.is_absolute():
            raise ExternalEvidenceAuthorityStateError("authority ledger path must be absolute")
        self.ledger_path = ledger_path
        self.expected_owner_uid = expected_owner_uid

    def provision_genesis(self, state: ExternalEvidenceAuthorityState) -> None:
        if state.epoch != 1 or state.previous_state_digest is not None:
            raise ExternalEvidenceAuthorityStateError("genesis authority state is invalid")
        ledger = ExternalEvidenceAuthorityLedger(entries=[state])
        raw = ledger.canonical_json_bytes()
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(
                self.ledger_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o444,
            )
        except FileExistsError:
            existing = load_external_evidence_authority_state(
                self.ledger_path, expected_owner_uid=self.expected_owner_uid
            )
            if existing != ledger:
                raise ExternalEvidenceAuthorityStateError(
                    "genesis authority state conflicts with existing ledger"
                ) from None
            return
        try:
            _write_all(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(self.ledger_path.parent)

    def rotate(
        self,
        state: ExternalEvidenceAuthorityState,
        *,
        crash_after_publish: bool = False,
    ) -> None:
        lock_path = self.ledger_path.with_suffix(self.ledger_path.suffix + ".lock")
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            ledger = load_external_evidence_authority_state(
                self.ledger_path, expected_owner_uid=self.expected_owner_uid
            )
            current = ledger.current
            if state == current:
                return
            expected_previous = "sha256:" + hashlib.sha256(
                current.canonical_json_bytes()
            ).hexdigest()
            if (
                state.authority_id != current.authority_id
                or state.epoch != current.epoch + 1
                or state.previous_state_digest != expected_previous
                or (
                    state.key_fingerprint != current.key_fingerprint
                    and state.key_fingerprint
                    in {entry.key_fingerprint for entry in ledger.entries}
                )
            ):
                raise ExternalEvidenceAuthorityStateError(
                    "authority rotation is not the exact next state"
                )
            next_ledger = ExternalEvidenceAuthorityLedger(entries=[*ledger.entries, state])
            self._replace(next_ledger.canonical_json_bytes())
            if crash_after_publish:
                raise RuntimeError("simulated broker crash after durable authority rotation")
        finally:
            with suppress(OSError):
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def promote_signed_snapshot(
        self,
        *,
        staged_root: Path,
        public_key: Path,
        now: datetime | None = None,
    ) -> ExternalEvidenceAuthorityState:
        """Independently verify staged authority files and promote exact derived state."""

        from tcfactory.v3.external_evidence import (  # local: avoid model cycle
            ExternalEvidenceAuthorityAnchor,
            ExternalEvidenceRevocationList,
            assert_privileged_read_only,
            load_verified_external_evidence_bytes,
        )

        verification_time = now or datetime.now(UTC)
        for protected in (staged_root, public_key):
            assert_privileged_read_only(protected)
        revocation_path = staged_root / "revocation-list.json"
        anchor_path = staged_root / "authority-anchor.json"
        for protected in (
            revocation_path,
            revocation_path.with_suffix(".json.sig"),
            anchor_path,
            anchor_path.with_suffix(".json.sig"),
        ):
            assert_privileged_read_only(protected)
        revocation_raw = load_verified_external_evidence_bytes(
            path=revocation_path,
            signature=revocation_path.with_suffix(".json.sig"),
            public_key=public_key,
        )
        anchor_raw = load_verified_external_evidence_bytes(
            path=anchor_path,
            signature=anchor_path.with_suffix(".json.sig"),
            public_key=public_key,
        )
        revocations = ExternalEvidenceRevocationList.model_validate_json(
            revocation_raw, strict=True
        )
        anchor = ExternalEvidenceAuthorityAnchor.model_validate_json(
            anchor_raw, strict=True
        )
        revocation_digest = "sha256:" + hashlib.sha256(
            revocations.canonical_json_bytes()
        ).hexdigest()
        if (
            revocations.authority_id != anchor.authority_id
            or revocations.issuer_id != anchor.issuer_id
            or revocations.key_id != anchor.key_id
            or revocations.epoch != anchor.epoch
            or anchor.current_revocation_digest != revocation_digest
            or anchor.previous_revocation_digest != revocations.previous_list_digest
            or verification_time >= revocations.expires_at
            or verification_time >= anchor.expires_at
        ):
            raise ExternalEvidenceAuthorityStateError(
                "staged external evidence authority snapshot is inconsistent or stale"
            )
        current = (
            None
            if anchor.epoch == 1
            else load_external_evidence_authority_state(
                self.ledger_path, expected_owner_uid=self.expected_owner_uid
            ).current
        )
        if current is not None and (
            anchor.epoch != current.epoch + 1
            or revocations.previous_list_digest != current.revocation_list_digest
        ):
            raise ExternalEvidenceAuthorityStateError(
                "staged authority snapshot does not extend monotonic state"
            )
        previous_state_digest: str | None = None
        if anchor.epoch > 1:
            assert current is not None
            previous_state_digest = "sha256:" + hashlib.sha256(
                current.canonical_json_bytes()
            ).hexdigest()
        state = ExternalEvidenceAuthorityState(
            authority_id=anchor.authority_id,
            epoch=anchor.epoch,
            anchor_digest="sha256:" + hashlib.sha256(anchor.canonical_json_bytes()).hexdigest(),
            revocation_list_digest=revocation_digest,
            key_fingerprint=key_fingerprint(public_key.read_bytes()),
            previous_state_digest=previous_state_digest,
            advanced_at=verification_time,
        )
        if state.epoch == 1:
            self.provision_genesis(state)
        else:
            self.rotate(state)
        return state

    def _replace(self, raw: bytes) -> None:
        directory = self.ledger_path.parent
        temporary = directory / f".{self.ledger_path.name}.{secrets.token_hex(8)}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        try:
            _write_all(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, self.ledger_path)
            os.chmod(self.ledger_path, 0o444)
            _fsync_directory(directory)
        except Exception:
            with suppress(OSError):
                temporary.unlink()
            raise


def _write_all(fd: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(fd, raw[offset:])
        if written <= 0:
            raise ExternalEvidenceAuthorityStateError("authority ledger write failed")
        offset += written


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
