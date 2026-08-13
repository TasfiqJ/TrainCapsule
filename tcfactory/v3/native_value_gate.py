"""V3.1 complete-substitute and decision-value gate.

This module deliberately separates deterministic candidate evaluation from authorization.
Candidate-visible code can calculate a proposed disposition, but only a cryptographically
verified independent machine-policy receipt may authorize the resulting maturity transition.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from pydantic import Field, model_validator

from tcfactory.v3.contracts_v31 import (
    ApprovedAgentAssistanceV31,
    CommercialState,
    DecisionValueDisposition,
    DecisionValueResultV31,
    EpistemicState,
    FreshnessState,
    MachinePolicyReceiptV31,
    NativeSubstituteBenchmarkV31,
    NativeSubstituteDisposition,
    NativeToolConfigurationV31,
    PolicyDecision,
    SourceFreshnessReceiptV31,
    TechnicalState,
    V31Model,
    ValueState,
)
from tcfactory.v3.enums import WorkStatus


class NativeValueGateError(RuntimeError):
    """Raised whenever benchmark or independent authority evidence fails closed."""


class ArtifactReader(Protocol):
    def read_exact(self, digest: str) -> bytes: ...


class FreshnessReceiptVerifier(Protocol):
    def verify(self, receipt: SourceFreshnessReceiptV31, *, now: datetime) -> None: ...


class MachineReceiptVerifier(Protocol):
    def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> None: ...


class NativeValueGatePolicyV31(V31Model):
    policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    policy_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    approved_native_substitute: list[NativeToolConfigurationV31] = Field(
        min_length=1, max_length=32
    )
    approved_agent_assistance: list[ApprovedAgentAssistanceV31] = Field(max_length=16)
    minimum_repetitions: int = Field(ge=2, le=1000)
    maximum_traincapsule_cost_ratio: float = Field(gt=0, le=1000)
    maximum_traincapsule_time_ratio: float = Field(gt=0, le=1000)
    required_allowed_claims: list[str] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_policy(self) -> NativeValueGatePolicyV31:
        if len({item.tool_name for item in self.approved_native_substitute}) != len(
            self.approved_native_substitute
        ):
            raise ValueError("approved substitute tool names must be unique")
        if len({item.system_id for item in self.approved_agent_assistance}) != len(
            self.approved_agent_assistance
        ):
            raise ValueError("approved agent-assistance systems must be unique")
        if len(set(self.required_allowed_claims)) != len(self.required_allowed_claims):
            raise ValueError("required allowed claims must be unique")
        return self


class AuthorizedValueTransitionV31(V31Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    candidate_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    benchmark_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    value_result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    machine_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    resulting_status: WorkStatus
    technical_ceiling: TechnicalState
    commercial_ceiling: CommercialState
    allowed_claims: list[str] = Field(min_length=1, max_length=64)
    forbidden_claims: list[str] = Field(max_length=64)


def evaluate_native_value_candidate(
    *,
    benchmark: NativeSubstituteBenchmarkV31,
    policy: NativeValueGatePolicyV31,
    candidate_sha: str,
    candidate_tree_sha: str,
    artifact_reader: ArtifactReader,
    freshness_receipts: list[SourceFreshnessReceiptV31],
    freshness_verifier: FreshnessReceiptVerifier,
    now: datetime | None = None,
) -> DecisionValueResultV31:
    """Derive a preliminary value result from exact bytes and verified freshness evidence."""

    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        benchmark.candidate_sha != candidate_sha
        or benchmark.candidate_tree_sha != candidate_tree_sha
    ):
        raise NativeValueGateError("benchmark candidate identity mismatch")
    if _canonical_models(benchmark.native_tool_names_versions_configs) != _canonical_models(
        policy.approved_native_substitute
    ):
        raise NativeValueGateError("benchmark does not cover the complete approved substitute")
    if _canonical_models(benchmark.approved_agent_assistance_baseline) != _canonical_models(
        policy.approved_agent_assistance
    ):
        raise NativeValueGateError("benchmark agent-assistance baseline is incomplete")

    receipt_digests: list[str] = []
    for receipt in freshness_receipts:
        freshness_verifier.verify(receipt, now=observed_now)
        if receipt.expires_at.astimezone(UTC) <= observed_now:
            raise NativeValueGateError("source freshness receipt is expired")
        if receipt.state is not FreshnessState.FRESH:
            raise NativeValueGateError("source freshness is not independently FRESH")
        receipt_digests.append(receipt.canonical_digest())
    if sorted(receipt_digests) != sorted(benchmark.source_freshness_receipts):
        raise NativeValueGateError("source freshness receipts do not match the benchmark")

    for digest in benchmark.raw_artifact_hashes:
        raw = artifact_reader.read_exact(digest)
        observed = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        if observed != digest:
            raise NativeValueGateError("benchmark raw artifact digest mismatch")

    derived_decision_changed = (
        benchmark.native_operational_decision != benchmark.traincapsule_operational_decision
    )
    if benchmark.decision_changed is not derived_decision_changed:
        raise NativeValueGateError("caller-authored decision change does not match evidence")
    reproducible = (
        benchmark.reproducibility.environment_digest == benchmark.environment_digest
        and benchmark.reproducibility.repetitions >= policy.minimum_repetitions
        and benchmark.reproducibility.matching_decision_count
        == benchmark.reproducibility.repetitions
    )
    expected_native = _native_disposition(
        benchmark,
        reproducible=reproducible,
        decision_changed=derived_decision_changed,
    )
    if benchmark.disposition is not expected_native:
        raise NativeValueGateError("caller-authored native disposition does not match evidence")
    disposition = _decision_value_disposition(
        benchmark,
        policy=policy,
        reproducible=reproducible,
        decision_changed=derived_decision_changed,
    )
    value_state, decision_changed = _value_state(disposition)
    comparison = benchmark.cost_time_resource_comparison
    rationale = (
        f"Native benchmark {benchmark.benchmark_id} produced {disposition.value}; "
        f"decisionChanged={str(decision_changed).lower()}, "
        f"nativeCost={comparison.native_cost}, traincapsuleCost={comparison.traincapsule_cost}, "
        f"nativeMinutes={comparison.native_minutes}, "
        f"traincapsuleMinutes={comparison.traincapsule_minutes}."
    )
    return DecisionValueResultV31(
        schema_version="3.1",
        work_item_id=benchmark.work_item_id,
        evaluated=True,
        disposition=disposition,
        native_benchmark_digest=benchmark.canonical_digest(),
        evidence_refs=benchmark.raw_artifact_hashes,
        original_experiment_cost=comparison.native_cost,
        proposed_experiment_cost=comparison.traincapsule_cost,
        original_experiment_minutes=comparison.native_minutes,
        proposed_experiment_minutes=comparison.traincapsule_minutes,
        decision_changed=decision_changed,
        rationale=rationale,
        value_state=value_state,
    )


def authorize_value_transition(
    *,
    benchmark: NativeSubstituteBenchmarkV31,
    value_result: DecisionValueResultV31,
    policy: NativeValueGatePolicyV31,
    receipt: MachinePolicyReceiptV31,
    receipt_verifier: MachineReceiptVerifier,
    now: datetime | None = None,
) -> AuthorizedValueTransitionV31:
    """Authorize a maturity transition only after external signature/revocation validation."""

    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    receipt_verifier.verify(receipt, now=observed_now)
    expected_native = benchmark.disposition
    expected_value = value_result.disposition
    if receipt.decision is not PolicyDecision.PASS:
        raise NativeValueGateError("machine policy did not authorize this candidate")
    if receipt.policy_id != policy.policy_id or receipt.policy_version != policy.policy_version:
        raise NativeValueGateError("machine receipt policy identity/version mismatch")
    if (
        receipt.work_item_id != benchmark.work_item_id
        or receipt.candidate_sha != benchmark.candidate_sha
        or receipt.candidate_tree_sha != benchmark.candidate_tree_sha
    ):
        raise NativeValueGateError("machine receipt candidate/work-item mismatch")
    if receipt.native_substitute_disposition is not expected_native:
        raise NativeValueGateError("machine receipt native disposition mismatch")
    if receipt.decision_value_disposition is not expected_value:
        raise NativeValueGateError("machine receipt value disposition mismatch")
    if not set(benchmark.raw_artifact_hashes).issubset(set(receipt.raw_evidence_artifact_hashes)):
        raise NativeValueGateError("machine receipt does not bind every benchmark artifact")
    if not set(benchmark.independent_oracle_ids).issubset(set(receipt.independent_oracle_ids)):
        raise NativeValueGateError("machine receipt does not bind every benchmark oracle")
    if not set(policy.required_allowed_claims).issubset(set(receipt.allowed_claims)):
        raise NativeValueGateError("machine receipt omits required bounded claims")
    if (
        benchmark.truth_state is not EpistemicState.EXTERNALLY_VERIFIED
        and receipt.commercial_maturity_ceiling is CommercialState.COMMERCIALLY_SUPPORTED
    ):
        raise NativeValueGateError("controlled evidence cannot authorize commercial support")

    status = _work_status(expected_value)
    if status is WorkStatus.PASSED_ENGINEERING and (
        receipt.engineering_maturity_ceiling is not TechnicalState.PASSED
        or receipt.commercial_maturity_ceiling is CommercialState.NOT_EVALUATED
    ):
        raise NativeValueGateError(
            "machine receipt maturity ceilings cannot authorize PASSED_ENGINEERING"
        )
    return AuthorizedValueTransitionV31(
        schema_version="3.1",
        work_item_id=benchmark.work_item_id,
        candidate_sha=benchmark.candidate_sha,
        candidate_tree_sha=benchmark.candidate_tree_sha,
        benchmark_digest=benchmark.canonical_digest(),
        value_result_digest=value_result.canonical_digest(),
        machine_receipt_digest=receipt.canonical_digest(),
        resulting_status=status,
        technical_ceiling=receipt.engineering_maturity_ceiling,
        commercial_ceiling=receipt.commercial_maturity_ceiling,
        allowed_claims=receipt.allowed_claims,
        forbidden_claims=receipt.forbidden_claims,
    )


def _native_disposition(
    benchmark: NativeSubstituteBenchmarkV31,
    *,
    reproducible: bool,
    decision_changed: bool,
) -> NativeSubstituteDisposition:
    if benchmark.truth_state is EpistemicState.UNKNOWN or not reproducible:
        return NativeSubstituteDisposition.UNKNOWN
    if decision_changed:
        return NativeSubstituteDisposition.INCREMENTAL_VALUE
    return NativeSubstituteDisposition.NATIVE_SUFFICIENT


def _decision_value_disposition(
    benchmark: NativeSubstituteBenchmarkV31,
    *,
    policy: NativeValueGatePolicyV31,
    reproducible: bool,
    decision_changed: bool,
) -> DecisionValueDisposition:
    if benchmark.truth_state is EpistemicState.UNKNOWN or not reproducible:
        return DecisionValueDisposition.EXTERNAL_EVIDENCE_REQUIRED
    if not decision_changed:
        return DecisionValueDisposition.NATIVE_WORKFLOW_SUFFICIENT
    comparison = benchmark.cost_time_resource_comparison
    cost_ratio = _ratio(comparison.traincapsule_cost, comparison.native_cost)
    time_ratio = comparison.traincapsule_minutes / comparison.native_minutes
    if (
        cost_ratio > policy.maximum_traincapsule_cost_ratio
        or time_ratio > policy.maximum_traincapsule_time_ratio
    ):
        return DecisionValueDisposition.TECHNICALLY_VALID_BUT_NOT_ECONOMIC
    return DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED


def _ratio(candidate: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else float("inf")
    return candidate / baseline


def _value_state(
    disposition: DecisionValueDisposition,
) -> tuple[ValueState, bool]:
    if disposition is DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED:
        return ValueState.INCREMENTAL_VALUE, True
    if disposition is DecisionValueDisposition.NATIVE_WORKFLOW_SUFFICIENT:
        return ValueState.NATIVE_SUFFICIENT, False
    if disposition in {
        DecisionValueDisposition.NO_INCREMENTAL_DECISION_VALUE,
        DecisionValueDisposition.TECHNICALLY_VALID_BUT_NOT_ECONOMIC,
    }:
        return ValueState.REJECTED, False
    return ValueState.NOT_EVALUATED, False


def _work_status(disposition: DecisionValueDisposition) -> WorkStatus:
    if disposition is DecisionValueDisposition.NATIVE_WORKFLOW_SUFFICIENT:
        return WorkStatus.NATIVE_SUFFICIENT
    if disposition in {
        DecisionValueDisposition.NO_INCREMENTAL_DECISION_VALUE,
        DecisionValueDisposition.TECHNICALLY_VALID_BUT_NOT_ECONOMIC,
    }:
        return WorkStatus.REJECTED_VALUE
    if disposition is DecisionValueDisposition.EXTERNAL_EVIDENCE_REQUIRED:
        return WorkStatus.WAITING_EXTERNAL
    return WorkStatus.PASSED_ENGINEERING


def _canonical_models(values: Sequence[V31Model]) -> list[bytes]:
    return sorted(
        json.dumps(
            value.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        for value in values
    )


NATIVE_VALUE_CONTRACTS: dict[str, type[V31Model]] = {
    "native-value-gate-policy": NativeValueGatePolicyV31,
    "authorized-value-transition": AuthorizedValueTransitionV31,
}
