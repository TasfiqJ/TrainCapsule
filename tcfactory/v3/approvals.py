"""Human approval records bound to exact candidates and artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import (
    ApprovalDecision,
    ApprovalScope,
    SignatureAlgorithm,
)

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class ApprovalReviewer(V3Model):
    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    organization: str = Field(min_length=1)


class ApprovalSignature(V3Model):
    algorithm: SignatureAlgorithm
    key_id: str = Field(min_length=1)
    value: str = Field(min_length=1)


class HumanApprovalRecord(V3Model):
    schema_version: int = Field(default=1, ge=1, le=1)
    approval_id: str = Field(pattern=r"^HAPR-[A-Z0-9_-]+$")
    scope: ApprovalScope
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_digests: dict[str, Digest] = Field(min_length=1)
    reviewer: ApprovalReviewer
    reviewer_qualification: list[str] = Field(min_length=1)
    decision: ApprovalDecision
    conditions: list[str]
    limitations: list[str]
    issued_at: datetime
    expires_at: datetime | None
    signature: ApprovalSignature
    synthetic_test_only: Literal[False] = False

    @model_validator(mode="after")
    def validate_approval(self) -> HumanApprovalRecord:
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValueError("approval expiry must be after issue time")
        if (
            self.decision is ApprovalDecision.APPROVED_WITH_CONDITIONS
            and not self.conditions
        ):
            raise ValueError("conditional approval requires conditions")
        return self

    def require_valid(
        self,
        *,
        scope: ApprovalScope,
        candidate_commit: str,
        artifact_digests: Mapping[str, str],
        signature_valid: bool,
        source_agent_writable: bool,
        now: datetime | None = None,
    ) -> None:
        """Verify exact binding, freshness, source trust, and approval decision."""

        checked_at = now or datetime.now(UTC)
        if self.scope is not scope:
            raise ValueError("approval scope does not match")
        if self.candidate_commit != candidate_commit:
            raise ValueError("approval candidate commit does not match")
        if dict(artifact_digests) != self.artifact_digests:
            raise ValueError("approval artifact digests do not match")
        if self.expires_at is not None and checked_at >= self.expires_at:
            raise ValueError("approval has expired")
        if self.decision not in {
            ApprovalDecision.APPROVED,
            ApprovalDecision.APPROVED_WITH_CONDITIONS,
        }:
            raise ValueError("approval decision does not authorize the action")
        if source_agent_writable:
            raise ValueError("AI-writable human approval is not trusted")
        if not signature_valid:
            raise ValueError("human approval signature is invalid")
