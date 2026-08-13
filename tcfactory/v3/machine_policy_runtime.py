"""Independent Phase 3 authorization for machine-policy review work items."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from tcfactory.v3.contracts_v31 import (
    ActivationMode,
    CommercialState,
    DecisionValueDisposition,
    GateResult,
    NativeSubstituteDisposition,
    PolicyDecision,
    TechnicalState,
    V31Model,
)
from tcfactory.v3.enums import Lane, RiskTier, WorkStatus
from tcfactory.v3.native_value_runtime import (
    NativeValueRuntimeError,
    Phase3NativeValueAuthority,
)


class MachinePolicyRuntimeError(RuntimeError):
    """The independent review receipt or its activation failed closed."""


class AuthorizedMachinePolicyReviewV31(V31Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    candidate_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    machine_receipt_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    machine_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_evidence_digests: list[str] = Field(min_length=1, max_length=128)
    resulting_status: WorkStatus
    engineering_ceiling: TechnicalState
    commercial_ceiling: CommercialState
    native_disposition: NativeSubstituteDisposition
    value_disposition: DecisionValueDisposition

    def completion_evidence_refs(self) -> list[str]:
        return [
            f"candidate-manifest:{self.candidate_manifest_digest}",
            f"machine-policy-receipt:{self.machine_receipt_digest}",
            f"activation-receipt:{self.activation_receipt_digest}",
            *(f"dependency-evidence:{digest}" for digest in self.dependency_evidence_digests),
        ]


def _authorized_status(
    *,
    decision: PolicyDecision,
    technical: TechnicalState,
    commercial: CommercialState,
    native: NativeSubstituteDisposition,
    value: DecisionValueDisposition,
) -> WorkStatus:
    if decision is not PolicyDecision.PASS:
        return WorkStatus.BLOCKED_POLICY
    if (
        native is NativeSubstituteDisposition.NATIVE_SUFFICIENT
        or value is DecisionValueDisposition.NATIVE_WORKFLOW_SUFFICIENT
    ):
        return WorkStatus.NATIVE_SUFFICIENT
    if value in {
        DecisionValueDisposition.NO_INCREMENTAL_DECISION_VALUE,
        DecisionValueDisposition.TECHNICALLY_VALID_BUT_NOT_ECONOMIC,
    }:
        return WorkStatus.REJECTED_VALUE
    if value is DecisionValueDisposition.EXTERNAL_EVIDENCE_REQUIRED:
        return WorkStatus.WAITING_EXTERNAL
    if (
        value is DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        and native is NativeSubstituteDisposition.INCREMENTAL_VALUE
        and technical is TechnicalState.PASSED
        and commercial is not CommercialState.NOT_EVALUATED
    ):
        return WorkStatus.PASSED_ENGINEERING
    return WorkStatus.BLOCKED_POLICY


def load_authorized_machine_policy_review(
    *,
    receipt_path: Path,
    activation_path: Path,
    authority: Phase3NativeValueAuthority,
    work_item_id: str,
    milestone_id: str,
    lane: Lane,
    risk_tier: RiskTier,
    candidate_sha: str,
    candidate_tree_sha: str,
    base_sha: str,
    candidate_manifest_digest: str,
    review_context_digest: str,
    dependency_evidence_digests: list[str],
    required_gate_results: Mapping[str, GateResult],
    expected_main_sha: str,
    source_generation_id: str,
    source_generation_digest: str,
    controller_binary_digest: str,
    controller_config_digest: str,
    now: datetime | None = None,
) -> AuthorizedMachinePolicyReviewV31:
    """Verify an exact independently signed review and derive its bounded transition."""

    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    if not dependency_evidence_digests or len(dependency_evidence_digests) != len(
        set(dependency_evidence_digests)
    ):
        raise MachinePolicyRuntimeError("dependency evidence roster is empty or duplicated")
    if not required_gate_results or any(
        result is not GateResult.PASS for result in required_gate_results.values()
    ):
        raise MachinePolicyRuntimeError("dependency gate roster is incomplete or non-passing")
    try:
        receipt = authority.verify_machine_receipt(
            receipt_path,
            candidate_sha=candidate_sha,
            candidate_tree_sha=candidate_tree_sha,
            base_sha=base_sha,
            work_item_id=work_item_id,
            candidate_manifest_digest=candidate_manifest_digest,
        )
    except NativeValueRuntimeError as exc:
        raise MachinePolicyRuntimeError(
            "independent machine-policy review receipt was rejected"
        ) from exc
    receipt_digest = receipt.canonical_digest()
    expected = {
        "milestone_id": milestone_id,
        "lane": lane,
        "risk_tier": risk_tier,
        "source_generation_id": source_generation_id,
        "source_generation_digest": source_generation_digest,
        "context_manifest_digest": review_context_digest,
        "task_packet_digest": review_context_digest,
        "checkpoint_digest": review_context_digest,
        "request_digest": review_context_digest,
    }
    for field, value in expected.items():
        if getattr(receipt, field) != value:
            raise MachinePolicyRuntimeError(f"machine-policy review {field} mismatch")
    if dict(receipt.required_gate_results) != dict(required_gate_results):
        raise MachinePolicyRuntimeError("machine-policy review gate roster mismatch")
    if set(receipt.raw_evidence_artifact_hashes) != set(dependency_evidence_digests):
        raise MachinePolicyRuntimeError("machine-policy review evidence roster mismatch")
    if receipt.expires_at.astimezone(UTC) <= observed_now:
        raise MachinePolicyRuntimeError("machine-policy review receipt is expired")
    try:
        activation = authority.verify_activation(
            activation_path,
            expected_main_sha=expected_main_sha,
            source_generation_id=source_generation_id,
            source_generation_digest=source_generation_digest,
            controller_binary_digest=controller_binary_digest,
            controller_config_digest=controller_config_digest,
        )
    except NativeValueRuntimeError as exc:
        raise MachinePolicyRuntimeError(
            "independent machine-policy review activation was rejected"
        ) from exc
    if (
        activation.mode is not ActivationMode.LIVE
        or activation.machine_policy_receipt_id != receipt.receipt_id
        or activation.machine_policy_receipt_digest != receipt_digest
        or activation.expires_at.astimezone(UTC) <= observed_now
    ):
        raise MachinePolicyRuntimeError(
            "LIVE activation does not bind the exact machine-policy review receipt"
        )
    status = _authorized_status(
        decision=receipt.decision,
        technical=receipt.engineering_maturity_ceiling,
        commercial=receipt.commercial_maturity_ceiling,
        native=receipt.native_substitute_disposition,
        value=receipt.decision_value_disposition,
    )
    return AuthorizedMachinePolicyReviewV31(
        schema_version="3.1",
        work_item_id=work_item_id,
        candidate_sha=candidate_sha,
        candidate_manifest_digest=candidate_manifest_digest,
        machine_receipt_id=receipt.receipt_id,
        machine_receipt_digest=receipt_digest,
        activation_receipt_digest=activation.canonical_digest(),
        dependency_evidence_digests=sorted(dependency_evidence_digests),
        resulting_status=status,
        engineering_ceiling=receipt.engineering_maturity_ceiling,
        commercial_ceiling=receipt.commercial_maturity_ceiling,
        native_disposition=receipt.native_substitute_disposition,
        value_disposition=receipt.decision_value_disposition,
    )
