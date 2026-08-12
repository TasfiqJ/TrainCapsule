"""External evidence records and fail-closed trust evaluation."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import Field

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import (
    ArtifactLocationClass,
    EvidenceType,
    SignatureAlgorithm,
)

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


class ExternalEvidenceReceipt(V3Model):
    receipt_version: int = Field(default=1, ge=1, le=1)
    receipt_id: str = Field(pattern=r"^XREC-[A-Z0-9_-]+$")
    evidence_type: EvidenceType
    subject_id: str = Field(min_length=1)
    issuer: EvidenceIssuer
    observed_at: datetime
    candidate_or_offer_identity: str | None = None
    outcome: str = Field(min_length=1)
    artifacts: list[EvidenceArtifact]
    limitations: list[str]
    signature: EvidenceSignature
    synthetic_test_only: bool

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


def _verify_detached_ed25519_signature(
    *, receipt: Path, signature: Path, public_key: Path
) -> None:
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
    if key_type.returncode != 0 or "ED25519" not in (
        key_type.stdout + key_type.stderr
    ).upper():
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


def load_verified_external_evidence(
    *,
    repo_root: Path,
    subject_id: str,
    trusted_root_environment_variable: str,
    trusted_public_key_environment_variable: str,
    environment: Mapping[str, str] | None = None,
) -> TrustedEvidenceRecord:
    """Load one subject-bound, non-agent-writable, Ed25519-verified receipt.

    Receipt discovery is deterministic: the trusted root contains
    ``<work-item-id>.json`` and its detached ``.sig``.  The repository never
    supplies a fallback, a validity boolean, or a path override.
    """

    environ = os.environ if environment is None else environment
    root_value = environ.get(trusted_root_environment_variable, "").strip()
    key_value = environ.get(trusted_public_key_environment_variable, "").strip()
    if not root_value or not key_value:
        raise ExternalEvidenceVerificationError(
            "trusted external evidence root or public key is not configured"
        )
    root = Path(root_value).expanduser().resolve()
    public_key = Path(key_value).expanduser().resolve()
    repository = repo_root.resolve()
    for protected in (root, public_key):
        try:
            protected.relative_to(repository)
        except ValueError:
            pass
        else:
            raise ExternalEvidenceVerificationError(
                "trusted external evidence must remain outside the repository"
            )
        _assert_privileged_read_only(protected)
    receipt_path = (root / f"{subject_id}.json").resolve()
    try:
        receipt_path.relative_to(root)
    except ValueError as exc:
        raise ExternalEvidenceVerificationError(
            "external evidence receipt path escapes its trusted root"
        ) from exc
    signature_path = receipt_path.with_suffix(receipt_path.suffix + ".sig")
    for protected in (receipt_path, signature_path):
        if not protected.is_file():
            raise ExternalEvidenceVerificationError(
                f"trusted external evidence is missing for {subject_id}"
            )
        _assert_privileged_read_only(protected)
    _verify_detached_ed25519_signature(
        receipt=receipt_path,
        signature=signature_path,
        public_key=public_key,
    )
    try:
        receipt = ExternalEvidenceReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
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
    record = TrustedEvidenceRecord(
        receipt=receipt,
        signature_valid=True,
        source_agent_writable=False,
    )
    record.require_commercial_trust()
    return record
