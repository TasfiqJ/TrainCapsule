"""External evidence records and fail-closed trust evaluation."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import (
    ArtifactLocationClass,
    EvidenceType,
    SignatureAlgorithm,
)
from tcfactory.v3.external_evidence_authority import (
    ExternalEvidenceAuthorityStateError,
    key_fingerprint,
    load_external_evidence_authority_state,
)

if TYPE_CHECKING:
    from tcfactory.v3.external_actions import ExternalActionOutcome

_ACTION_RESPONSE_CONSUMPTION_WINDOW = timedelta(minutes=15)

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class ExternalEvidenceVerificationError(RuntimeError):
    """A claimed outside fact could not be verified at the trusted boundary."""


class EvidenceIssuer(V3Model):
    id: str = Field(min_length=1)
    authority: str = Field(min_length=1)


class EvidenceArtifact(V3Model):
    name: str = Field(min_length=1)
    digest: Digest
    location_class: ArtifactLocationClass


class EvidenceSignature(V3Model):
    algorithm: SignatureAlgorithm
    key_id: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ExternalActionResponseBinding(V3Model):
    """Signed reverse binding from an outside response to one exact delivery."""

    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    action_id: str = Field(min_length=1)
    action_digest: Digest
    payload_digest: Digest
    delivery_digest: Digest
    backend_delivery_id: str = Field(min_length=1)
    idempotency_key: Digest
    delivery_generation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    response_receipt_id: str = Field(pattern=r"^XREC-[A-Z0-9_-]+$")
    response_nonce: str = Field(pattern=r"^[0-9a-f]{32,128}$")
    channel: Literal["EMAIL", "CRM", "CALENDAR"]
    recipient: str = Field(min_length=1, max_length=320)
    template_id: str = Field(min_length=1, max_length=128)
    requested_at: datetime
    delivered_at: datetime
    response_observed_at: datetime
    response_expires_at: datetime


class CustomerDecisionValueAttestation(V3Model):
    """Two separately asserted customer facts within one signed receipt."""

    decision_changed_or_materially_strengthened: bool
    value_exceeds_price_and_retained_effort: bool
    observed_price_microusd: int = Field(gt=0, le=10**15)
    retained_effort_minutes: int = Field(ge=0, le=10**9)
    attribution_artifact_digests: list[Digest] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_attribution(self) -> CustomerDecisionValueAttestation:
        if len(self.attribution_artifact_digests) != len(set(self.attribution_artifact_digests)):
            raise ValueError("customer decision/value attribution must be unique")
        return self


class EvidenceCorrelationIdentity(V3Model):
    """Stable identities used to correlate separately signed commercial facts."""

    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    customer_identity_digest: Digest | None = None
    family_identity_digest: Digest | None = None
    offer_identity_digest: Digest | None = None
    pack_identity_digest: Digest | None = None

    @model_validator(mode="after")
    def has_commercial_identity(self) -> EvidenceCorrelationIdentity:
        if not any(
            (
                self.customer_identity_digest,
                self.family_identity_digest,
                self.offer_identity_digest,
                self.pack_identity_digest,
            )
        ):
            raise ValueError("external evidence correlation lacks a commercial identity")
        return self


class ExternalEvidenceReceipt(V3Model):
    receipt_version: int = Field(default=1, ge=1, le=1)
    receipt_id: str = Field(pattern=r"^XREC-[A-Z0-9_-]+$")
    evidence_type: EvidenceType
    subject_id: str = Field(min_length=1)
    issuer: EvidenceIssuer
    issued_at: datetime
    observed_at: datetime
    expires_at: datetime
    revocation_epoch: int = Field(ge=0)
    revoked: bool
    nonce: str = Field(pattern=r"^[0-9a-f]{32,128}$")
    candidate_or_offer_identity: str | None = None
    outcome: str = Field(min_length=1)
    artifacts: list[EvidenceArtifact] = Field(min_length=1, max_length=10_000)
    limitations: list[str]
    signature: EvidenceSignature
    synthetic_test_only: bool
    action_response_binding: ExternalActionResponseBinding | None = None
    customer_decision_value: CustomerDecisionValueAttestation | None = None
    correlation_identity: EvidenceCorrelationIdentity | None = None

    @model_validator(mode="after")
    def unique_artifact_roster(self) -> ExternalEvidenceReceipt:
        """One outside fact may not be multiplied by repeating its artifact."""

        names = [artifact.name for artifact in self.artifacts]
        digests = [artifact.digest for artifact in self.artifacts]
        identities = [
            (artifact.name, artifact.digest, artifact.location_class) for artifact in self.artifacts
        ]
        if len(names) != len(set(names)):
            raise ValueError("external evidence artifact names must be unique")
        if len(digests) != len(set(digests)):
            raise ValueError("external evidence artifact digests must be unique")
        if len(identities) != len(set(identities)):
            raise ValueError("external evidence artifact identities must be unique")
        if self.customer_decision_value is not None:
            if self.evidence_type is not EvidenceType.DECISION_CHANGED:
                raise ValueError(
                    "customer decision/value attestation requires DECISION_CHANGED evidence"
                )
            artifact_digests = set(digests)
            if not set(self.customer_decision_value.attribution_artifact_digests).issubset(
                artifact_digests
            ):
                raise ValueError(
                    "customer decision/value attribution is absent from receipt artifacts"
                )
        if self.correlation_identity is not None:
            candidate_identity = self.candidate_or_offer_identity
            if candidate_identity != self.correlation_identity.candidate_sha:
                raise ValueError(
                    "external evidence correlation candidate does not match its receipt"
                )
        return self

    def require_current(self, *, now: datetime) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("external evidence verification time must be timezone-aware")
        if (
            self.revoked
            or self.issued_at > self.observed_at
            or self.observed_at > now
            or now >= self.expires_at
        ):
            raise ValueError("external evidence receipt is stale, revoked, or impossible")

    def require_commercial_trust(
        self,
        *,
        signature_valid: bool,
        source_agent_writable: bool,
    ) -> None:
        """Reject synthetic, unsigned, or AI-writable commercial evidence."""

        if self.synthetic_test_only:
            raise ValueError("synthetic evidence cannot advance commercial maturity")
        if source_agent_writable:
            raise ValueError("AI-writable external evidence is not trusted")
        if not signature_valid:
            raise ValueError("external evidence signature is invalid")
        if not self.artifacts:
            raise ValueError("trusted external evidence requires at least one artifact")

    def require_exact_action_response(
        self,
        outcome: ExternalActionOutcome,
        *,
        now: datetime,
    ) -> None:
        """Require this signed outside response to follow one exact delivered action."""

        if outcome.status.value != "SENT" or outcome.delivery_receipt is None:
            raise ValueError("external response requires an exact SENT delivery")
        binding = self.action_response_binding
        if binding is None:
            raise ValueError("external response omitted its exact action binding")
        request = outcome.request
        delivery = outcome.delivery_receipt
        expected = {
            "work_item_id": outcome.work_item_id,
            "candidate_sha": outcome.candidate_sha,
            "action_id": outcome.action_id,
            "action_digest": outcome.request_digest,
            "payload_digest": delivery.payload_digest,
            "delivery_digest": delivery.delivery_digest,
            "backend_delivery_id": delivery.backend_delivery_id,
            "idempotency_key": delivery.idempotency_key,
            "delivery_generation_id": delivery.delivery_generation_id,
            "response_receipt_id": self.receipt_id,
            "response_nonce": binding.response_nonce,
            "channel": request.channel.value,
            "recipient": request.recipient,
            "template_id": request.template_id,
            "requested_at": request.requested_at,
            "delivered_at": delivery.delivered_at,
            "response_observed_at": self.observed_at,
            "response_expires_at": binding.response_expires_at,
        }
        if binding.model_dump(mode="python") != expected:
            raise ValueError("external response does not match the exact delivered action")
        if self.subject_id != outcome.work_item_id:
            raise ValueError("external response subject does not match the delivered action")
        if self.candidate_or_offer_identity != outcome.candidate_sha:
            raise ValueError("external response candidate identity mismatch")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("external response verification time must be timezone-aware")
        if (
            request.requested_at > delivery.delivered_at
            or delivery.delivered_at > self.observed_at
            or self.observed_at > now
            or binding.response_expires_at <= self.observed_at
            or binding.response_expires_at - self.observed_at > _ACTION_RESPONSE_CONSUMPTION_WINDOW
            or now >= binding.response_expires_at
        ):
            raise ValueError("external response timing is stale or impossible")


class ExternalEvidenceRevocationList(V3Model):
    revocation_version: int = Field(default=1, ge=1, le=1)
    authority_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    issuer_id: str = Field(min_length=1, max_length=256)
    key_id: str = Field(min_length=1, max_length=256)
    epoch: int = Field(ge=1)
    previous_list_digest: Digest | None
    issued_at: datetime
    expires_at: datetime
    revoked_receipt_ids: list[str] = Field(max_length=100_000)
    revoked_nonces: list[str] = Field(max_length=100_000)

    @model_validator(mode="after")
    def validate_chain(self) -> ExternalEvidenceRevocationList:
        if (self.epoch == 1) != (self.previous_list_digest is None):
            raise ValueError("revocation-list previous digest does not match its epoch")
        if self.issued_at >= self.expires_at:
            raise ValueError("revocation-list validity window is invalid")
        if len(self.revoked_receipt_ids) != len(set(self.revoked_receipt_ids)) or len(
            self.revoked_nonces
        ) != len(set(self.revoked_nonces)):
            raise ValueError("revocation-list entries must be unique")
        return self


class ExternalEvidenceAuthorityAnchor(V3Model):
    anchor_version: int = Field(default=1, ge=1, le=1)
    authority_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    issuer_id: str = Field(min_length=1, max_length=256)
    key_id: str = Field(min_length=1, max_length=256)
    epoch: int = Field(ge=1)
    current_revocation_digest: Digest
    previous_revocation_digest: Digest | None
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_chain(self) -> ExternalEvidenceAuthorityAnchor:
        if (self.epoch == 1) != (self.previous_revocation_digest is None):
            raise ValueError("authority-anchor previous digest does not match its epoch")
        if self.issued_at >= self.expires_at:
            raise ValueError("authority-anchor validity window is invalid")
        return self


class TrustedEvidenceRecord(V3Model):
    """Runtime verification result; this is never authored by the work agent."""

    receipt: ExternalEvidenceReceipt
    signature_valid: bool
    source_agent_writable: bool

    def require_commercial_trust(self) -> ExternalEvidenceReceipt:
        self.receipt.require_commercial_trust(
            signature_valid=self.signature_valid,
            source_agent_writable=self.source_agent_writable,
        )
        return self.receipt


@dataclass(frozen=True)
class VerifiedExternalEvidencePayload:
    record: TrustedEvidenceRecord
    canonical_bytes: bytes
    canonical_digest: str
    authority_payloads: Mapping[str, bytes]
    authority_digests: Mapping[str, str]


def _assert_privileged_read_only(path: Path) -> None:
    """Require the receipt trust root to be outside the agent's writable authority."""

    for protected in (path, *path.parents):
        try:
            metadata = protected.stat()
        except OSError as exc:
            raise ExternalEvidenceVerificationError(
                f"trusted external evidence path is unavailable: {protected}"
            ) from exc
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ExternalEvidenceVerificationError(
                "trusted external evidence and every parent must be root-owned and "
                f"not group/world writable: {protected}"
            )


def _verify_detached_ed25519_signature(*, receipt: Path, signature: Path, public_key: Path) -> None:
    """Cryptographically verify the exact receipt bytes with a launcher-pinned key."""

    key_type = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkey",
            "-pubin",
            "-in",
            str(public_key),
            "-text",
            "-noout",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if key_type.returncode != 0 or "ED25519" not in (key_type.stdout + key_type.stderr).upper():
        raise ExternalEvidenceVerificationError(
            "external evidence public key is not a valid Ed25519 public key"
        )
    verified = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-rawin",
            "-in",
            str(receipt),
            "-sigfile",
            str(signature),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if verified.returncode != 0:
        raise ExternalEvidenceVerificationError(
            "external evidence receipt signature verification failed"
        )


def assert_privileged_read_only(path: Path) -> None:
    """Public trust-boundary check shared by independent receipt validators."""

    _assert_privileged_read_only(path)


def verify_detached_ed25519_signature(*, receipt: Path, signature: Path, public_key: Path) -> None:
    """Public exact-byte Ed25519 verifier for independent receipt validators."""

    _verify_detached_ed25519_signature(
        receipt=receipt,
        signature=signature,
        public_key=public_key,
    )


def load_verified_external_evidence_bytes(
    *, path: Path, signature: Path, public_key: Path
) -> bytes:
    metadata = path.stat()
    _verify_detached_ed25519_signature(
        receipt=path,
        signature=signature,
        public_key=public_key,
    )
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise ExternalEvidenceVerificationError(
            "trusted external evidence changed after signature verification"
        ) from exc
    try:
        opened = os.fstat(fd)
        if (
            (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
            or opened.st_size != metadata.st_size
            or opened.st_mtime_ns != metadata.st_mtime_ns
            or opened.st_size > 2_000_000
        ):
            raise ExternalEvidenceVerificationError(
                "trusted external evidence changed after signature verification"
            )
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != opened.st_size:
            raise ExternalEvidenceVerificationError(
                "trusted external evidence changed while reading"
            )
        return raw
    finally:
        os.close(fd)


def load_verified_external_evidence(
    *,
    repo_root: Path,
    subject_id: str,
    trusted_root_environment_variable: str,
    trusted_public_key_environment_variable: str,
    trusted_authority_state_environment_variable: str = ("TCF_EXTERNAL_EVIDENCE_AUTHORITY_STATE"),
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> TrustedEvidenceRecord:
    """Load one subject-bound, non-agent-writable, Ed25519-verified receipt.

    Receipt discovery is deterministic: the trusted root contains
    ``<work-item-id>.json`` and its detached ``.sig``.  The repository never
    supplies a fallback, a validity boolean, or a path override.
    """

    environ = os.environ if environment is None else environment
    root_value = environ.get(trusted_root_environment_variable, "").strip()
    key_value = environ.get(trusted_public_key_environment_variable, "").strip()
    authority_state_value = environ.get(trusted_authority_state_environment_variable, "").strip()
    if not root_value or not key_value or not authority_state_value:
        raise ExternalEvidenceVerificationError(
            "trusted external evidence root, public key, or authority state is not configured"
        )
    root = Path(root_value).expanduser().resolve()
    public_key = Path(key_value).expanduser().resolve()
    authority_state_path = Path(authority_state_value).expanduser().resolve()
    root_identity = root.stat()
    key_identity = public_key.stat()
    repository = repo_root.resolve()
    for protected in (root, public_key, authority_state_path):
        try:
            protected.relative_to(repository)
        except ValueError:
            pass
        else:
            raise ExternalEvidenceVerificationError(
                "trusted external evidence must remain outside the repository"
            )
        _assert_privileged_read_only(protected)
    names = (
        f"{subject_id}.json",
        f"{subject_id}.json.sig",
        "revocation-list.json",
        "revocation-list.json.sig",
        "authority-anchor.json",
        "authority-anchor.json.sig",
    )
    paths = tuple((root / name).resolve() for name in names)
    for protected in paths:
        try:
            protected.relative_to(root)
        except ValueError as exc:
            raise ExternalEvidenceVerificationError(
                "external evidence authority path escapes its trusted root"
            ) from exc
        if not protected.is_file():
            raise ExternalEvidenceVerificationError(
                f"trusted external evidence authority file is missing: {protected.name}"
            )
        _assert_privileged_read_only(protected)
    (
        receipt_path,
        signature_path,
        revocation_path,
        revocation_signature_path,
        anchor_path,
        anchor_signature_path,
    ) = paths
    try:
        receipt = ExternalEvidenceReceipt.model_validate_json(
            load_verified_external_evidence_bytes(
                path=receipt_path,
                signature=signature_path,
                public_key=public_key,
            )
        )
        revocations = ExternalEvidenceRevocationList.model_validate_json(
            load_verified_external_evidence_bytes(
                path=revocation_path,
                signature=revocation_signature_path,
                public_key=public_key,
            )
        )
        anchor = ExternalEvidenceAuthorityAnchor.model_validate_json(
            load_verified_external_evidence_bytes(
                path=anchor_path,
                signature=anchor_signature_path,
                public_key=public_key,
            )
        )
    except (OSError, ValueError) as exc:
        raise ExternalEvidenceVerificationError(
            "trusted external evidence receipt is unreadable or invalid"
        ) from exc
    if receipt.subject_id != subject_id:
        raise ExternalEvidenceVerificationError(
            "external evidence receipt subject does not match the work item"
        )
    if receipt.signature.algorithm is not SignatureAlgorithm.ED25519:
        raise ExternalEvidenceVerificationError(
            "external evidence receipt does not declare Ed25519"
        )
    verification_time = now or datetime.now(UTC)
    revocation_digest = "sha256:" + hashlib.sha256(revocations.canonical_json_bytes()).hexdigest()
    if (
        revocations.authority_id != anchor.authority_id
        or revocations.issuer_id != anchor.issuer_id
        or revocations.key_id != anchor.key_id
        or revocations.issuer_id != receipt.issuer.id
        or revocations.key_id != receipt.signature.key_id
        or revocations.epoch != anchor.epoch
        or receipt.revocation_epoch > revocations.epoch
        or anchor.current_revocation_digest != revocation_digest
        or anchor.previous_revocation_digest != revocations.previous_list_digest
    ):
        raise ExternalEvidenceVerificationError(
            "external evidence authority, key, issuer, epoch, or digest chain mismatch"
        )
    if (
        revocations.issued_at > verification_time
        or verification_time >= revocations.expires_at
        or anchor.issued_at > verification_time
        or verification_time >= anchor.expires_at
    ):
        raise ExternalEvidenceVerificationError("external evidence revocation authority is stale")
    if (
        receipt.receipt_id in revocations.revoked_receipt_ids
        or receipt.nonce in revocations.revoked_nonces
    ):
        raise ExternalEvidenceVerificationError("external evidence receipt is revoked")
    current_root_identity = root.stat()
    current_key_identity = public_key.stat()
    if (current_root_identity.st_dev, current_root_identity.st_ino) != (
        root_identity.st_dev,
        root_identity.st_ino,
    ) or (current_key_identity.st_dev, current_key_identity.st_ino) != (
        key_identity.st_dev,
        key_identity.st_ino,
    ):
        raise ExternalEvidenceVerificationError(
            "external evidence authority root or key changed during verification"
        )
    try:
        monotonic = load_external_evidence_authority_state(authority_state_path).current
    except ExternalEvidenceAuthorityStateError as exc:
        raise ExternalEvidenceVerificationError(
            "external evidence monotonic authority state is invalid"
        ) from exc
    anchor_digest = "sha256:" + hashlib.sha256(anchor.canonical_json_bytes()).hexdigest()
    observed_key_fingerprint = key_fingerprint(public_key.read_bytes())
    if (
        monotonic.authority_id != anchor.authority_id
        or monotonic.epoch != anchor.epoch
        or monotonic.anchor_digest != anchor_digest
        or monotonic.revocation_list_digest != revocation_digest
        or monotonic.key_fingerprint != observed_key_fingerprint
    ):
        raise ExternalEvidenceVerificationError(
            "external evidence authority pair conflicts with monotonic state"
        )
    record = TrustedEvidenceRecord(
        receipt=receipt,
        signature_valid=True,
        source_agent_writable=False,
    )
    record.require_commercial_trust()
    receipt.require_current(now=verification_time)
    return record


def load_verified_external_evidence_payload(
    *,
    repo_root: Path,
    subject_id: str,
    trusted_root_environment_variable: str,
    trusted_public_key_environment_variable: str,
    trusted_authority_state_environment_variable: str = ("TCF_EXTERNAL_EVIDENCE_AUTHORITY_STATE"),
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> VerifiedExternalEvidencePayload:
    """Return exact canonical bytes only after the trusted receipt verifies."""

    record = load_verified_external_evidence(
        repo_root=repo_root,
        subject_id=subject_id,
        trusted_root_environment_variable=trusted_root_environment_variable,
        trusted_public_key_environment_variable=trusted_public_key_environment_variable,
        trusted_authority_state_environment_variable=(trusted_authority_state_environment_variable),
        environment=environment,
        now=now,
    )
    canonical = record.receipt.canonical_json_bytes()
    environ = os.environ if environment is None else environment
    root = Path(environ[trusted_root_environment_variable]).expanduser().resolve()
    public_key = Path(environ[trusted_public_key_environment_variable]).expanduser().resolve()
    authority_state = (
        Path(environ[trusted_authority_state_environment_variable]).expanduser().resolve()
    )
    authority_payloads = {
        "receipt": canonical,
        "receipt-signature": (root / f"{subject_id}.json.sig").read_bytes(),
        "revocation-list": (root / "revocation-list.json").read_bytes(),
        "revocation-list-signature": (root / "revocation-list.json.sig").read_bytes(),
        "authority-anchor": (root / "authority-anchor.json").read_bytes(),
        "authority-anchor-signature": (root / "authority-anchor.json.sig").read_bytes(),
        "monotonic-authority-state": authority_state.read_bytes(),
        "authority-public-key": public_key.read_bytes(),
    }
    # Re-run the full verification after snapshotting so a concurrent authority
    # rotation cannot produce a mixed payload accepted by the controller.
    confirmed = load_verified_external_evidence(
        repo_root=repo_root,
        subject_id=subject_id,
        trusted_root_environment_variable=trusted_root_environment_variable,
        trusted_public_key_environment_variable=trusted_public_key_environment_variable,
        trusted_authority_state_environment_variable=(trusted_authority_state_environment_variable),
        environment=environment,
        now=now,
    )
    if confirmed.receipt.canonical_json_bytes() != canonical:
        raise ExternalEvidenceVerificationError(
            "external evidence authority changed while snapshotting"
        )
    current_payloads = {
        "receipt": confirmed.receipt.canonical_json_bytes(),
        "receipt-signature": (root / f"{subject_id}.json.sig").read_bytes(),
        "revocation-list": (root / "revocation-list.json").read_bytes(),
        "revocation-list-signature": (root / "revocation-list.json.sig").read_bytes(),
        "authority-anchor": (root / "authority-anchor.json").read_bytes(),
        "authority-anchor-signature": (root / "authority-anchor.json.sig").read_bytes(),
        "monotonic-authority-state": authority_state.read_bytes(),
        "authority-public-key": public_key.read_bytes(),
    }
    if current_payloads != authority_payloads:
        raise ExternalEvidenceVerificationError(
            "external evidence authority changed while snapshotting"
        )
    authority_digests = {
        name: "sha256:" + hashlib.sha256(raw).hexdigest()
        for name, raw in authority_payloads.items()
    }
    return VerifiedExternalEvidencePayload(
        record=record,
        canonical_bytes=canonical,
        canonical_digest="sha256:" + hashlib.sha256(canonical).hexdigest(),
        authority_payloads=authority_payloads,
        authority_digests=authority_digests,
    )
