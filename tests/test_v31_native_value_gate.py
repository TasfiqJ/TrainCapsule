from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tcfactory.v3.contracts_v31 import (
    BenchmarkReproducibilityV31,
    CommercialState,
    CostTimeResourceComparisonV31,
    DecisionValueDisposition,
    EpistemicState,
    FreshnessState,
    GateResult,
    MachinePolicyReceiptV31,
    NativeSubstituteBenchmarkV31,
    NativeSubstituteDisposition,
    NativeToolConfigurationV31,
    PolicyDecision,
    SourceFreshnessReceiptV31,
    TechnicalState,
)
from tcfactory.v3.enums import Lane, RiskTier, WorkStatus
from tcfactory.v3.native_value_gate import (
    NativeValueGateError,
    NativeValueGatePolicyV31,
    authorize_value_transition,
    evaluate_native_value_candidate,
)

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
SHA = "a" * 40
TREE = "b" * 40
BASE = "c" * 40
RAW_NATIVE = b"native evidence"
RAW_TC = b"TrainCapsule evidence"
DIGEST_NATIVE = "sha256:" + __import__("hashlib").sha256(RAW_NATIVE).hexdigest()
DIGEST_TC = "sha256:" + __import__("hashlib").sha256(RAW_TC).hexdigest()
DIGEST_OTHER = "sha256:" + "d" * 64


class MemoryArtifacts:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values

    def read_exact(self, digest: str) -> bytes:
        if digest not in self.values:
            raise NativeValueGateError("missing raw artifact")
        return self.values[digest]


class FreshnessVerifier:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject

    def verify(self, receipt: SourceFreshnessReceiptV31, *, now: datetime) -> None:
        if self.reject:
            raise NativeValueGateError("freshness signature rejected")
        assert now == NOW
        assert receipt.signature_algorithm == "ed25519"


class ReceiptVerifier:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject

    def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> None:
        if self.reject:
            raise NativeValueGateError("receipt revoked")
        assert now == NOW
        assert receipt.expires_at > now


def freshness(*, state: FreshnessState = FreshnessState.FRESH) -> SourceFreshnessReceiptV31:
    stale = state in {FreshnessState.STALE, FreshnessState.RECHECK_REQUIRED}
    return SourceFreshnessReceiptV31(
        schema_version="3.1",
        receipt_id="FRESHNESS:NATIVE:001",
        generation_id="SOURCE:V31",
        generation_digest=DIGEST_OTHER,
        source_id="SOURCE:NATIVE:001",
        source_digest=DIGEST_NATIVE,
        observed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        state=state,
        conflict_artifact_digests=[DIGEST_OTHER] if stale else [],
        wedge_work_item_id="V3-PROD-001" if stale else None,
        issuer_id="VERIFIER:SOURCE:001",
        issuer_key_id="KEY:SOURCE:001",
        signature_algorithm="ed25519",
        signature="1" * 96,
    )


def policy() -> NativeValueGatePolicyV31:
    return NativeValueGatePolicyV31(
        schema_version="3.1",
        policy_id="POLICY:ZERO-HUMAN",
        approved_native_substitute=[
            NativeToolConfigurationV31(
                schema_version="3.1",
                tool_name="PyTorch Flight Recorder",
                tool_version="2.5.1",
                configuration_digest=DIGEST_OTHER,
            )
        ],
        approved_agent_assistance=[],
        minimum_repetitions=2,
        maximum_traincapsule_cost_ratio=1.0,
        maximum_traincapsule_time_ratio=1.0,
        required_allowed_claims=["CLAIM:ENGINEERING-PASS"],
    )


def benchmark(
    source_receipt: SourceFreshnessReceiptV31,
    *,
    decision_changed: bool = True,
    disposition: NativeSubstituteDisposition = NativeSubstituteDisposition.INCREMENTAL_VALUE,
    truth_state: EpistemicState = EpistemicState.CONTROLLED,
    traincapsule_cost: float = 25.0,
    traincapsule_minutes: float = 10.0,
    repetitions: int = 2,
    matching: int = 2,
    tools: list[NativeToolConfigurationV31] | None = None,
) -> NativeSubstituteBenchmarkV31:
    inventory = tools or policy().approved_native_substitute
    return NativeSubstituteBenchmarkV31(
        schema_version="3.1",
        benchmark_id="BENCHMARK:NATIVE:001",
        work_item_id="V3-PROD-001",
        case_id="CASE:NATIVE:001",
        candidate_sha=SHA,
        candidate_tree_sha=TREE,
        environment_digest=DIGEST_TC,
        baseline_environment_digest=DIGEST_NATIVE,
        candidate_environment_digest=DIGEST_TC,
        source_freshness_receipts=[source_receipt.canonical_digest()],
        native_tool_names_versions_configs=inventory,
        approved_agent_assistance_baseline=[],
        native_tool=inventory[0].tool_name,
        native_tool_version=inventory[0].tool_version,
        native_inputs=[DIGEST_NATIVE],
        native_outputs=[DIGEST_NATIVE],
        native_findings=[DIGEST_NATIVE],
        native_operational_decision="Retain the existing action.",
        traincapsule_incremental_capability="Apply an incident-derived qualification contract.",
        traincapsule_outputs=[DIGEST_TC],
        traincapsule_operational_decision=(
            "Reject the unsafe candidate." if decision_changed else "Retain the existing action."
        ),
        native_evidence_digests=[DIGEST_NATIVE],
        candidate_evidence_digests=[DIGEST_TC],
        incident_derived_contract_digests=[DIGEST_NATIVE],
        independent_oracle_ids=["ORACLE:NATIVE:001"],
        oracle_identity="ORACLE:NATIVE:001",
        issuer_identity="VERIFIER:LOCAL:001",
        native_effort_minutes=30.0,
        candidate_effort_minutes=traincapsule_minutes,
        cost_time_resource_comparison=CostTimeResourceComparisonV31(
            schema_version="3.1",
            native_cost=100.0,
            traincapsule_cost=traincapsule_cost,
            native_minutes=30.0,
            traincapsule_minutes=traincapsule_minutes,
            native_resources=["flight-recorder", "approved-local-analysis"],
            traincapsule_resources=["traincapsule-local"],
        ),
        reproducibility=BenchmarkReproducibilityV31(
            schema_version="3.1",
            repetitions=repetitions,
            matching_decision_count=matching,
            command_digests=[DIGEST_NATIVE],
            environment_digest=DIGEST_TC,
        ),
        limitations=["Controlled evidence is not payment, adoption, or commercial proof."],
        truth_state=truth_state,
        raw_artifact_hashes=[DIGEST_NATIVE, DIGEST_TC],
        decision_changed=decision_changed,
        disposition=disposition,
    )


def evaluate(
    item: NativeSubstituteBenchmarkV31,
    source_receipt: SourceFreshnessReceiptV31,
):
    return evaluate_native_value_candidate(
        benchmark=item,
        policy=policy(),
        candidate_sha=SHA,
        candidate_tree_sha=TREE,
        artifact_reader=MemoryArtifacts({DIGEST_NATIVE: RAW_NATIVE, DIGEST_TC: RAW_TC}),
        freshness_receipts=[source_receipt],
        freshness_verifier=FreshnessVerifier(),
        now=NOW,
    )


def machine_receipt(
    item: NativeSubstituteBenchmarkV31,
    value_disposition: DecisionValueDisposition,
    **updates: Any,
) -> MachinePolicyReceiptV31:
    payload: dict[str, Any] = {
        "schema_version": "3.1",
        "receipt_id": "RECEIPT:VALUE:001",
        "policy_id": "POLICY:ZERO-HUMAN",
        "policy_version": "3.1.0",
        "issuer_id": "VERIFIER:LOCAL:001",
        "issuer_key_id": "KEY:ED25519:001",
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(hours=1),
        "revocation_epoch": 1,
        "nonce": "0123456789abcdef",
        "request_digest": DIGEST_OTHER,
        "work_item_id": item.work_item_id,
        "milestone_id": "M1_PRODUCT_WEDGE",
        "lane": Lane.PRODUCT,
        "risk_tier": RiskTier.STANDARD,
        "candidate_sha": item.candidate_sha,
        "candidate_tree_sha": item.candidate_tree_sha,
        "base_sha": BASE,
        "source_generation_id": "SOURCE:V31",
        "source_generation_digest": DIGEST_OTHER,
        "context_manifest_digest": DIGEST_OTHER,
        "task_packet_digest": DIGEST_OTHER,
        "candidate_manifest_digest": DIGEST_OTHER,
        "checkpoint_digest": DIGEST_OTHER,
        "required_gate_results": {"GATE:QUALITY": GateResult.PASS},
        "private_gate_suite_id": "FULL-RELEASE-V31",
        "private_gate_runner_digest": DIGEST_OTHER,
        "independent_oracle_ids": item.independent_oracle_ids,
        "raw_evidence_artifact_hashes": item.raw_artifact_hashes,
        "native_substitute_disposition": item.disposition,
        "decision_value_disposition": value_disposition,
        "engineering_maturity_ceiling": TechnicalState.PASSED,
        "commercial_maturity_ceiling": CommercialState.PILOT_ELIGIBLE,
        "allowed_claims": ["CLAIM:ENGINEERING-PASS"],
        "forbidden_claims": ["CLAIM:COMMERCIAL-SUPPORT"],
        "publication_scope": ["packages/traincapsule-core/**"],
        "decision": PolicyDecision.PASS,
        "signature_algorithm": "ed25519",
        "signature": "2" * 96,
    }
    payload.update(updates)
    return MachinePolicyReceiptV31.model_validate(payload, strict=True)


def test_incremental_decision_value_requires_exact_evidence_and_external_authority() -> None:
    current = freshness()
    item = benchmark(current)
    result = evaluate(item, current)
    assert result.disposition is DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
    transition = authorize_value_transition(
        benchmark=item,
        value_result=result,
        policy=policy(),
        receipt=machine_receipt(item, result.disposition),
        receipt_verifier=ReceiptVerifier(),
        now=NOW,
    )
    assert transition.resulting_status is WorkStatus.PASSED_ENGINEERING
    assert transition.commercial_ceiling is CommercialState.PILOT_ELIGIBLE


def test_same_operational_decision_is_native_sufficient_not_product_success() -> None:
    current = freshness()
    item = benchmark(
        current,
        decision_changed=False,
        disposition=NativeSubstituteDisposition.NATIVE_SUFFICIENT,
    )
    result = evaluate(item, current)
    assert result.disposition is DecisionValueDisposition.NATIVE_WORKFLOW_SUFFICIENT
    transition = authorize_value_transition(
        benchmark=item,
        value_result=result,
        policy=policy(),
        receipt=machine_receipt(item, result.disposition),
        receipt_verifier=ReceiptVerifier(),
        now=NOW,
    )
    assert transition.resulting_status is WorkStatus.NATIVE_SUFFICIENT


def test_changed_decision_that_is_not_economic_is_rejected_value() -> None:
    current = freshness()
    item = benchmark(current, traincapsule_cost=200.0, traincapsule_minutes=60.0)
    result = evaluate(item, current)
    assert result.disposition is DecisionValueDisposition.TECHNICALLY_VALID_BUT_NOT_ECONOMIC
    transition = authorize_value_transition(
        benchmark=item,
        value_result=result,
        policy=policy(),
        receipt=machine_receipt(item, result.disposition),
        receipt_verifier=ReceiptVerifier(),
        now=NOW,
    )
    assert transition.resulting_status is WorkStatus.REJECTED_VALUE


def test_caller_authored_disposition_and_weak_substitute_fail_closed() -> None:
    current = freshness()
    forged = benchmark(
        current,
        decision_changed=False,
        disposition=NativeSubstituteDisposition.NATIVE_SUFFICIENT,
    ).model_copy(
        update={
            "decision_changed": True,
            "disposition": NativeSubstituteDisposition.INCREMENTAL_VALUE,
        }
    )
    with pytest.raises(NativeValueGateError, match="does not match evidence"):
        evaluate(forged, current)
    weak = benchmark(
        current,
        tools=[
            NativeToolConfigurationV31(
                schema_version="3.1",
                tool_name="Deliberately weak echo tool",
                tool_version="0.0.1",
                configuration_digest=DIGEST_OTHER,
            )
        ],
    )
    with pytest.raises(NativeValueGateError, match="complete approved substitute"):
        evaluate(weak, current)


def test_stale_unsigned_missing_or_substituted_evidence_fails_closed() -> None:
    current = freshness()
    item = benchmark(current)
    with pytest.raises(NativeValueGateError, match="freshness signature rejected"):
        evaluate_native_value_candidate(
            benchmark=item,
            policy=policy(),
            candidate_sha=SHA,
            candidate_tree_sha=TREE,
            artifact_reader=MemoryArtifacts({DIGEST_NATIVE: RAW_NATIVE, DIGEST_TC: RAW_TC}),
            freshness_receipts=[current],
            freshness_verifier=FreshnessVerifier(reject=True),
            now=NOW,
        )
    with pytest.raises(NativeValueGateError, match="missing raw artifact"):
        evaluate_native_value_candidate(
            benchmark=item,
            policy=policy(),
            candidate_sha=SHA,
            candidate_tree_sha=TREE,
            artifact_reader=MemoryArtifacts({DIGEST_NATIVE: RAW_NATIVE}),
            freshness_receipts=[current],
            freshness_verifier=FreshnessVerifier(),
            now=NOW,
        )
    with pytest.raises(NativeValueGateError, match="digest mismatch"):
        evaluate_native_value_candidate(
            benchmark=item,
            policy=policy(),
            candidate_sha=SHA,
            candidate_tree_sha=TREE,
            artifact_reader=MemoryArtifacts({DIGEST_NATIVE: b"substituted", DIGEST_TC: RAW_TC}),
            freshness_receipts=[current],
            freshness_verifier=FreshnessVerifier(),
            now=NOW,
        )


def test_irreproducible_benchmark_cannot_launder_incremental_value() -> None:
    current = freshness()
    item = benchmark(current, repetitions=3, matching=2)
    with pytest.raises(NativeValueGateError, match="does not match evidence"):
        evaluate(item, current)


def test_machine_receipt_mismatch_revocation_and_commercial_overclaim_fail() -> None:
    current = freshness()
    item = benchmark(current)
    result = evaluate(item, current)
    receipt = machine_receipt(item, result.disposition)
    with pytest.raises(NativeValueGateError, match="receipt revoked"):
        authorize_value_transition(
            benchmark=item,
            value_result=result,
            policy=policy(),
            receipt=receipt,
            receipt_verifier=ReceiptVerifier(reject=True),
            now=NOW,
        )
    wrong_candidate = receipt.model_copy(update={"candidate_sha": "f" * 40})
    with pytest.raises(NativeValueGateError, match="candidate/work-item mismatch"):
        authorize_value_transition(
            benchmark=item,
            value_result=result,
            policy=policy(),
            receipt=wrong_candidate,
            receipt_verifier=ReceiptVerifier(),
            now=NOW,
        )
    commercial = receipt.model_copy(
        update={"commercial_maturity_ceiling": CommercialState.COMMERCIALLY_SUPPORTED}
    )
    with pytest.raises(NativeValueGateError, match="cannot authorize commercial support"):
        authorize_value_transition(
            benchmark=item,
            value_result=result,
            policy=policy(),
            receipt=commercial,
            receipt_verifier=ReceiptVerifier(),
            now=NOW,
        )
