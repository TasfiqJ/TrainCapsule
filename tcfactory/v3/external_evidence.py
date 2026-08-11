"""External evidence records and fail-closed trust evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import (
    ArtifactLocationClass,
    EvidenceType,
    SignatureAlgorithm,
)

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


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
