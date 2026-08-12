"""Small V3 pipeline services that keep authority boundaries explicit."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field

from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model
from tcfactory.v3.enums import PolicyScope, WorkStatus
from tcfactory.v3.external_evidence import TrustedEvidenceRecord


class FindingOwner(StrEnum):
    PRODUCT = "PRODUCT"
    FACTORY = "FACTORY"
    EXTERNAL = "EXTERNAL"
    MACHINE_POLICY = "MACHINE_POLICY"


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
    "config/",
    "docs/source-of-truth/",
    "docs/migrations/V3_OWNER_DIRECTIVES.md",
    "SOURCE_PRECEDENCE.md",
    "factory/roadmap/",
    "factory/private-gates/",
    "factory/policy/",
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


def assert_candidate_scope(
    changed_paths: list[str], *, allowed_paths: list[str], forbidden_paths: list[str]
) -> None:
    """Fail closed when a candidate escapes its packet or changes policy authority."""

    normalized = [PurePosixPath(path).as_posix().lstrip("./") for path in changed_paths]
    if any(path.startswith(_PROTECTED_FACTORY_PATHS) for path in normalized):
        assert_factory_repair_scope(normalized)
    escaped = [
        path
        for path in normalized
        if not any(fnmatchcase(path, pattern) for pattern in allowed_paths)
        or any(fnmatchcase(path, pattern) for pattern in forbidden_paths)
    ]
    if escaped:
        raise ValueError(f"candidate changed paths outside its immutable packet: {escaped}")


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


class MachinePolicyGateReceipt(V3Model):
    policy: Literal["OWNER_DIRECTED_ZERO_HUMAN"] = "OWNER_DIRECTED_ZERO_HUMAN"
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    artifact_digests: dict[str, str]
    owner_directives_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


def evaluate_machine_policy_gate(
    receipt: MachinePolicyGateReceipt | None,
    *,
    scope: PolicyScope,
    candidate_sha: str,
    artifact_digests: Mapping[str, str],
    owner_directives_digest: str,
) -> GateDecision:
    del scope
    if receipt is None:
        return GateDecision(
            passed=False,
            state=WorkStatus.BLOCKED_POLICY,
            authority_ref=None,
            reason="candidate-bound machine policy receipt is required",
        )
    if receipt.candidate_sha != candidate_sha:
        raise ValueError("machine policy receipt candidate SHA mismatch")
    if receipt.artifact_digests != dict(artifact_digests):
        raise ValueError("machine policy receipt artifact digests mismatch")
    if receipt.owner_directives_digest != owner_directives_digest:
        raise ValueError("machine policy receipt owner-directive digest mismatch")
    return GateDecision(
        passed=True,
        state=WorkStatus.PASSED_ENGINEERING,
        authority_ref=receipt.owner_directives_digest,
        reason="deterministic owner-directed machine policy matches exact candidate",
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
    machine_policy_gate_passed: bool
    external_gate_passed: bool

    def require_releasable(self, observed_sha: str) -> None:
        if observed_sha != self.candidate_sha:
            raise ValueError("release candidate SHA changed after validation")
        if not self.factory_ci_passed or not self.product_ci_passed:
            raise ValueError("release candidate CI is incomplete")
        if not self.machine_policy_gate_passed or not self.external_gate_passed:
            raise ValueError("release candidate lacks required external authority")
