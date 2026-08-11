"""Small V3 pipeline services that keep authority boundaries explicit."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import Field

from tcfactory.v3.approvals import HumanApprovalRecord
from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model
from tcfactory.v3.enums import ApprovalScope, WorkStatus
from tcfactory.v3.external_evidence import TrustedEvidenceRecord


class FindingOwner(StrEnum):
    PRODUCT = "PRODUCT"
    FACTORY = "FACTORY"
    EXTERNAL = "EXTERNAL"
    HUMAN = "HUMAN"


class V3Finding(V3Model):
    finding_id: str = Field(pattern=r"^FIND-[A-Z0-9_-]+$")
    summary: str = Field(min_length=1)
    artifact_path: str | None = None
    artifact_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    advisory: bool = False
    declared_owner: FindingOwner | None = None


class RoutedFinding(V3Model):
    finding: V3Finding
    owner: FindingOwner
    blocking: bool


_FACTORY_PREFIXES = ("tcfactory/", "factory/", "config/", "prompts/", "scripts/")
_PROTECTED_FACTORY_PATHS = (
    "docs/source-of-truth/",
    "config/human_approval.yaml",
    "config/external_evidence.yaml",
    "config/commercial_maturity.yaml",
    "factory/roadmap/",
    "factory/private-gates/",
)


def route_finding(finding: V3Finding) -> RoutedFinding:
    """Route by declared owner or referenced surface; advisory findings never block."""

    if finding.declared_owner is not None:
        owner = finding.declared_owner
    elif finding.artifact_path:
        normalized = PurePosixPath(finding.artifact_path).as_posix().lstrip("./")
        owner = (
            FindingOwner.FACTORY
            if normalized.startswith(_FACTORY_PREFIXES)
            else FindingOwner.PRODUCT
        )
    else:
        owner = FindingOwner.PRODUCT
    return RoutedFinding(finding=finding, owner=owner, blocking=not finding.advisory)


def assert_factory_repair_scope(changed_paths: list[str]) -> None:
    """Prevent self-repair from changing normative, trust, approval, or value authority."""

    forbidden = [
        path
        for path in changed_paths
        if PurePosixPath(path).as_posix().lstrip("./").startswith(_PROTECTED_FACTORY_PATHS)
    ]
    if forbidden:
        raise ValueError(f"factory repair attempted protected authority changes: {forbidden}")


class CandidateLifecycle(V3Model):
    work_item_id: str
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    status: WorkStatus
    preserved: bool


class GateDecision(V3Model):
    passed: bool
    state: WorkStatus
    authority_ref: str | None
    reason: str


def evaluate_human_gate(
    approval: HumanApprovalRecord | None,
    *,
    scope: ApprovalScope,
    candidate_sha: str,
    artifact_digests: Mapping[str, str],
    signature_valid: bool,
) -> GateDecision:
    if approval is None:
        return GateDecision(
            passed=False,
            state=WorkStatus.WAITING_HUMAN,
            authority_ref=None,
            reason="external human approval is required",
        )
    approval.require_valid(
        scope=scope,
        candidate_commit=candidate_sha,
        artifact_digests=artifact_digests,
        signature_valid=signature_valid,
        source_agent_writable=False,
    )
    return GateDecision(
        passed=True,
        state=WorkStatus.PASSED_ENGINEERING,
        authority_ref=approval.approval_id,
        reason="trusted human approval matches exact candidate and artifacts",
    )


def evaluate_external_gate(record: TrustedEvidenceRecord | None) -> GateDecision:
    if record is None:
        return GateDecision(
            passed=False,
            state=WorkStatus.WAITING_EXTERNAL,
            authority_ref=None,
            reason="trusted external evidence receipt is required",
        )
    receipt = record.require_commercial_trust()
    return GateDecision(
        passed=True,
        state=WorkStatus.PASSED_ENGINEERING,
        authority_ref=receipt.receipt_id,
        reason="trusted external evidence receipt validated",
    )


class ReleaseCandidate(V3Model):
    work_item_id: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    factory_ci_passed: bool
    product_ci_passed: bool
    human_gate_passed: bool
    external_gate_passed: bool

    def require_releasable(self, observed_sha: str) -> None:
        if observed_sha != self.candidate_sha:
            raise ValueError("release candidate SHA changed after validation")
        if not self.factory_ci_passed or not self.product_ci_passed:
            raise ValueError("release candidate CI is incomplete")
        if not self.human_gate_passed or not self.external_gate_passed:
            raise ValueError("release candidate lacks required external authority")
