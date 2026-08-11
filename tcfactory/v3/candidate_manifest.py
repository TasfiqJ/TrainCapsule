"""Immutable V3 candidate manifest and artifact-substitution defense."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model, verify_bound_payloads
from tcfactory.v3.enums import ApprovalScope, ReleaseDecision

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class ExecutorIdentity(V3Model):
    backend: str = Field(min_length=1)
    adapter: str = Field(min_length=1)
    model: str = Field(min_length=1)
    session_id: str | None = None


class StageArtifactBinding(V3Model):
    stage: str = Field(min_length=1)
    name: str = Field(min_length=1)
    digest: Digest


class GateBinding(V3Model):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    result: str = Field(min_length=1)
    evidence_digest: Digest


class FindingBinding(V3Model):
    fingerprint: str = Field(min_length=1)
    disposition: str = Field(min_length=1)
    artifact_digest: Digest


class ApprovalBinding(V3Model):
    approval_id: str = Field(pattern=r"^HAPR-[A-Z0-9_-]+$")
    scope: ApprovalScope
    record_digest: Digest


class ExternalEvidenceBinding(V3Model):
    receipt_id: str = Field(pattern=r"^XREC-[A-Z0-9_-]+$")
    record_digest: Digest


class CandidateManifest(V3Model):
    manifest_version: int = Field(default=3, ge=3, le=3)
    base_sha: GitSha
    candidate_sha: GitSha
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    packet_digest: Digest
    context_digest: Digest
    executor: ExecutorIdentity
    stage_outputs: list[StageArtifactBinding]
    gates: list[GateBinding]
    findings: list[FindingBinding]
    approvals: list[ApprovalBinding]
    external_evidence: list[ExternalEvidenceBinding]
    checkpoint_digest: Digest
    release_decision: ReleaseDecision
    created_at: datetime

    @model_validator(mode="after")
    def unique_bindings(self) -> CandidateManifest:
        groups = {
            "stage artifacts": [f"{item.stage}:{item.name}" for item in self.stage_outputs],
            "gates": [item.name for item in self.gates],
            "findings": [item.fingerprint for item in self.findings],
            "approvals": [item.approval_id for item in self.approvals],
            "external evidence": [item.receipt_id for item in self.external_evidence],
        }
        for label, identifiers in groups.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"duplicate {label} binding")
        return self

    def bound_digests(self) -> dict[str, str]:
        """Return every external payload name and its immutable digest."""

        bindings = {
            "packet": self.packet_digest,
            "context": self.context_digest,
            "checkpoint": self.checkpoint_digest,
        }
        bindings.update(
            {
                f"stage:{item.stage}:{item.name}": item.digest
                for item in self.stage_outputs
            }
        )
        bindings.update({f"gate:{item.name}": item.evidence_digest for item in self.gates})
        bindings.update(
            {
                f"finding:{item.fingerprint}": item.artifact_digest
                for item in self.findings
            }
        )
        bindings.update(
            {f"approval:{item.approval_id}": item.record_digest for item in self.approvals}
        )
        bindings.update(
            {
                f"external:{item.receipt_id}": item.record_digest
                for item in self.external_evidence
            }
        )
        return bindings

    def verify_artifacts(self, artifacts: Mapping[str, bytes]) -> None:
        """Fail on missing, extra, or substituted candidate artifacts."""

        verify_bound_payloads(self.bound_digests(), artifacts)
