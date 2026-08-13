from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tcfactory.v3.candidate_manifest import (
    CandidateManifest,
    ExecutorIdentity,
    GateBinding,
    StageArtifactBinding,
)
from tcfactory.v3.contracts_v31 import (
    ActivationMode,
    ActivationReceiptV31,
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
from tcfactory.v3.enums import Lane, ReleaseDecision, RiskTier, WorkStatus
from tcfactory.v3.machine_policy_runtime import (
    MachinePolicyRuntimeError,
    load_authorized_machine_policy_review,
)
from tcfactory.v3.native_value_gate import (
    NativeValueGateError,
    NativeValueGatePolicyV31,
    authorize_value_transition,
    evaluate_native_value_candidate,
)
from tcfactory.v3.native_value_runtime import (
    BENCHMARK_BINDING,
    BENCHMARK_FILE,
    FRESHNESS_DIRECTORY,
    POLICY_BINDING,
    POLICY_FILE,
    VALUE_RESULT_BINDING,
    VALUE_RESULT_FILE,
    ContentAddressedRuntimeArtifacts,
    NativeValueRuntimeError,
    load_authorized_native_value_transition,
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
        generation_id="source:v31",
        generation_digest=DIGEST_OTHER,
        source_id="SOURCE:NATIVE:001",
        source_digest=DIGEST_NATIVE,
        observed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(minutes=55),
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
        policy_version="3.1.0",
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
        "source_generation_id": "source:v31",
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


class RuntimeAuthority:
    def __init__(
        self,
        receipt: MachinePolicyReceiptV31,
        activation: ActivationReceiptV31,
        *,
        revoked: bool = False,
    ) -> None:
        self.receipt = receipt
        self.activation = activation
        self.revoked = revoked

    def verify_machine_receipt(self, receipt_path: Path, **expected: object):
        if self.revoked:
            raise NativeValueRuntimeError("receipt is revoked")
        observed = MachinePolicyReceiptV31.model_validate_json(
            receipt_path.read_bytes(), strict=True
        )
        if observed.canonical_digest() != self.receipt.canonical_digest():
            raise NativeValueRuntimeError("receipt was substituted")
        if observed.expires_at <= NOW:
            raise NativeValueRuntimeError("receipt is expired")
        for field, value in expected.items():
            if hasattr(observed, field) and getattr(observed, field) != value:
                raise NativeValueRuntimeError(f"receipt {field} mismatch")
        return observed

    def verify_activation(self, activation_path: Path, **expected: object):
        observed = ActivationReceiptV31.model_validate_json(
            activation_path.read_bytes(), strict=True
        )
        if observed.canonical_digest() != self.activation.canonical_digest():
            raise NativeValueRuntimeError("activation was substituted")
        if observed.expires_at <= NOW:
            raise NativeValueRuntimeError("activation is expired")
        field_names = {
            "expected_main_sha": "verified_main_sha",
            "source_generation_id": "source_generation_id",
            "source_generation_digest": "source_generation_digest",
            "controller_binary_digest": "controller_binary_digest",
            "controller_config_digest": "controller_config_digest",
        }
        for requested, field in field_names.items():
            if getattr(observed, field) != expected[requested]:
                raise NativeValueRuntimeError(f"activation {field} mismatch")
        return observed


def runtime_bundle(tmp_path: Path) -> dict[str, Any]:
    source_receipt = freshness()
    item = benchmark(source_receipt)
    value = evaluate(item, source_receipt)
    artifact_dir = tmp_path / "runtime"
    freshness_dir = artifact_dir / FRESHNESS_DIRECTORY
    freshness_dir.mkdir(parents=True)
    benchmark_raw = item.canonical_json_bytes()
    value_raw = value.canonical_json_bytes()
    policy_raw = policy().canonical_json_bytes()
    (artifact_dir / BENCHMARK_FILE).write_bytes(benchmark_raw)
    (artifact_dir / VALUE_RESULT_FILE).write_bytes(value_raw)
    (artifact_dir / POLICY_FILE).write_bytes(policy_raw)
    (freshness_dir / f"{source_receipt.canonical_digest()[7:]}.json").write_bytes(
        source_receipt.canonical_json_bytes()
    )
    raw_root = tmp_path / "raw"
    for digest, raw in ((DIGEST_NATIVE, RAW_NATIVE), (DIGEST_TC, RAW_TC)):
        path = raw_root / "sha256" / digest[7:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    benchmark_digest = "sha256:" + __import__("hashlib").sha256(benchmark_raw).hexdigest()
    value_digest = "sha256:" + __import__("hashlib").sha256(value_raw).hexdigest()
    policy_digest = "sha256:" + __import__("hashlib").sha256(policy_raw).hexdigest()
    manifest = CandidateManifest(
        manifest_version=3,
        base_sha=BASE,
        candidate_sha=SHA,
        candidate_tree_sha=TREE,
        work_item_id=item.work_item_id,
        packet_digest=DIGEST_OTHER,
        context_digest=DIGEST_OTHER,
        executor=ExecutorIdentity(backend="fixture", adapter="fixture"),
        stage_outputs=[
            StageArtifactBinding(
                stage="machine_policy",
                name=BENCHMARK_BINDING,
                digest=benchmark_digest,
            ),
            StageArtifactBinding(
                stage="machine_policy", name=VALUE_RESULT_BINDING, digest=value_digest
            ),
            StageArtifactBinding(stage="machine_policy", name=POLICY_BINDING, digest=policy_digest),
        ],
        gates=[
            GateBinding(
                name="GATE:QUALITY",
                version="3.1.0",
                result="PASS",
                evidence_digest=DIGEST_OTHER,
            )
        ],
        findings=[],
        external_evidence=[],
        checkpoint_digest=DIGEST_OTHER,
        release_decision=ReleaseDecision.APPROVED_FOR_AUTOMATED_PULL_REQUEST,
        created_at=NOW,
    )
    manifest_raw = manifest.canonical_json_bytes()
    manifest_path = tmp_path / "candidate-manifest.json"
    manifest_path.write_bytes(manifest_raw)
    manifest_digest = "sha256:" + __import__("hashlib").sha256(manifest_raw).hexdigest()
    receipt = machine_receipt(
        item,
        value.disposition,
        candidate_manifest_digest=manifest_digest,
        raw_evidence_artifact_hashes=[
            *item.raw_artifact_hashes,
            source_receipt.canonical_digest(),
        ],
    )
    receipt_root = tmp_path / "receipts"
    receipt_path = receipt_root / "machine-policy" / item.work_item_id / f"{SHA}.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(receipt.canonical_json_bytes())
    activation = ActivationReceiptV31(
        schema_version="3.1",
        receipt_id="ACTIVATION:VALUE:001",
        verified_main_sha=SHA,
        machine_environment_digest=DIGEST_OTHER,
        source_generation_id="source:v31",
        source_generation_digest=DIGEST_OTHER,
        controller_binary_digest=DIGEST_OTHER,
        controller_config_digest=DIGEST_OTHER,
        machine_environment_path="runtime/machine-environment.json",
        controller_binary_path="tcfactory/v3/controller.py",
        controller_config_path="config/factory.yaml",
        machine_policy_receipt_id=receipt.receipt_id,
        machine_policy_receipt_digest=receipt.canonical_digest(),
        mode=ActivationMode.LIVE,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=55),
        revocation_epoch=1,
        nonce="activation-nonce-0123456789",
        issuer_id="VERIFIER:LOCAL:001",
        issuer_key_id="KEY:ED25519:001",
        signature_algorithm="ed25519",
        signature="3" * 96,
    )
    activation_path = tmp_path / "activation.json"
    activation_path.write_bytes(activation.canonical_json_bytes())
    return {
        "artifact_directory": artifact_dir,
        "candidate_manifest_path": manifest_path,
        "raw_artifacts": ContentAddressedRuntimeArtifacts(raw_root),
        "receipt_root": receipt_root,
        "activation_path": activation_path,
        "authority": RuntimeAuthority(receipt, activation),
        "freshness_verifier": FreshnessVerifier(),
        "work_item_id": item.work_item_id,
        "candidate_sha": SHA,
        "candidate_tree_sha": TREE,
        "base_sha": BASE,
        "expected_main_sha": SHA,
            "source_generation_id": "source:v31",
        "source_generation_digest": DIGEST_OTHER,
        "controller_binary_digest": DIGEST_OTHER,
        "controller_config_digest": DIGEST_OTHER,
        "now": NOW,
        "receipt": receipt,
        "activation": activation,
    }


def runtime_arguments(fixture: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fixture.items() if key not in {"receipt", "activation"}}


def test_runtime_loader_requires_manifest_receipt_activation_and_raw_evidence(
    tmp_path: Path,
) -> None:
    fixture = runtime_bundle(tmp_path)
    authorization = load_authorized_native_value_transition(**runtime_arguments(fixture))
    assert authorization.transition.resulting_status is WorkStatus.PASSED_ENGINEERING
    assert authorization.transition.machine_receipt_digest == fixture["receipt"].canonical_digest()
    assert authorization.activation_receipt_digest == fixture["activation"].canonical_digest()
    refs = authorization.completion_evidence_refs()
    assert f"candidate-manifest:{authorization.candidate_manifest_digest}" in refs
    assert f"machine-policy-receipt:{authorization.transition.machine_receipt_digest}" in refs
    assert BENCHMARK_BINDING != VALUE_RESULT_BINDING


def test_runtime_loader_rejects_substituted_benchmark_and_raw_artifact(tmp_path: Path) -> None:
    fixture = runtime_bundle(tmp_path)
    benchmark_path = fixture["artifact_directory"] / BENCHMARK_FILE
    benchmark_path.write_bytes(benchmark_path.read_bytes() + b" ")
    with pytest.raises(NativeValueRuntimeError, match="benchmark"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "raw-substitution")
    raw_store = fixture["raw_artifacts"]
    (raw_store.root / "sha256" / DIGEST_TC[7:]).write_bytes(b"attacker substitution")
    with pytest.raises(NativeValueRuntimeError, match="raw evidence"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


def test_runtime_loader_rejects_stale_revoked_or_wrong_candidate(tmp_path: Path) -> None:
    fixture = runtime_bundle(tmp_path)
    fixture["freshness_verifier"] = FreshnessVerifier(reject=True)
    with pytest.raises(NativeValueRuntimeError, match="replay"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "revoked")
    fixture["authority"] = RuntimeAuthority(fixture["receipt"], fixture["activation"], revoked=True)
    with pytest.raises(NativeValueRuntimeError, match="revoked"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "candidate")
    fixture["candidate_sha"] = "f" * 40
    with pytest.raises(NativeValueRuntimeError, match="candidate identity"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "work-item")
    fixture["work_item_id"] = "V3-PROD-999"
    with pytest.raises(NativeValueRuntimeError, match="candidate identity"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "tree")
    fixture["candidate_tree_sha"] = "e" * 40
    with pytest.raises(NativeValueRuntimeError, match="candidate identity"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


def test_runtime_loader_rejects_receipt_or_activation_substitution(tmp_path: Path) -> None:
    fixture = runtime_bundle(tmp_path)
    receipt_path = (
        fixture["receipt_root"] / "machine-policy" / fixture["work_item_id"] / f"{SHA}.json"
    )
    receipt_payload = json.loads(receipt_path.read_bytes())
    receipt_payload["signature"] = "4" * 96
    receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")
    with pytest.raises(NativeValueRuntimeError, match="substituted"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "activation")
    activation_payload = json.loads(fixture["activation_path"].read_bytes())
    activation_payload["signature"] = "5" * 96
    fixture["activation_path"].write_text(json.dumps(activation_payload), encoding="utf-8")
    with pytest.raises(NativeValueRuntimeError, match="activation was substituted"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baseSha", "f" * 40),
        ("sourceGenerationDigest", "sha256:" + "e" * 64),
        ("contextManifestDigest", "sha256:" + "e" * 64),
        ("taskPacketDigest", "sha256:" + "e" * 64),
        ("checkpointDigest", "sha256:" + "e" * 64),
        ("requiredGateResults", {"GATE:SPOOF": "PASS"}),
    ],
)
def test_runtime_loader_rejects_receipt_execution_context_laundering(
    tmp_path: Path, field: str, value: object
) -> None:
    fixture = runtime_bundle(tmp_path)
    receipt_path = (
        fixture["receipt_root"] / "machine-policy" / fixture["work_item_id"] / f"{SHA}.json"
    )
    payload = json.loads(receipt_path.read_bytes())
    payload[field] = value
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    laundered = MachinePolicyReceiptV31.model_validate_json(json.dumps(payload), strict=True)
    fixture["authority"] = RuntimeAuthority(laundered, fixture["activation"])
    with pytest.raises(
        NativeValueRuntimeError, match="execution context|candidate gates|base_sha mismatch"
    ):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


@pytest.mark.parametrize(
    ("name", "message"),
    [
        (VALUE_RESULT_FILE, "value result"),
        (POLICY_FILE, "policy"),
    ],
)
def test_runtime_loader_rejects_value_or_policy_tamper(
    tmp_path: Path, name: str, message: str
) -> None:
    fixture = runtime_bundle(tmp_path)
    path = fixture["artifact_directory"] / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(NativeValueRuntimeError, match=message):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


def test_runtime_loader_rejects_expired_activation(tmp_path: Path) -> None:
    fixture = runtime_bundle(tmp_path)
    expired = fixture["activation"].model_copy(
        update={
            "issued_at": NOW - timedelta(hours=2),
            "expires_at": NOW - timedelta(hours=1),
        }
    )
    fixture["activation_path"].write_bytes(expired.canonical_json_bytes())
    fixture["authority"] = RuntimeAuthority(fixture["receipt"], expired)
    with pytest.raises(NativeValueRuntimeError, match="expired"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


def test_runtime_loader_rejects_missing_bundle_receipt_or_activation(tmp_path: Path) -> None:
    fixture = runtime_bundle(tmp_path / "bundle")
    (fixture["artifact_directory"] / VALUE_RESULT_FILE).unlink()
    with pytest.raises(NativeValueRuntimeError):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "receipt")
    receipt_path = (
        fixture["receipt_root"] / "machine-policy" / fixture["work_item_id"] / f"{SHA}.json"
    )
    receipt_path.unlink()
    with pytest.raises(FileNotFoundError):
        load_authorized_native_value_transition(**runtime_arguments(fixture))

    fixture = runtime_bundle(tmp_path / "activation")
    fixture["activation_path"].unlink()
    with pytest.raises(FileNotFoundError):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


def test_runtime_loader_rejects_expired_machine_receipt(tmp_path: Path) -> None:
    fixture = runtime_bundle(tmp_path)
    expired = fixture["receipt"].model_copy(
        update={
            "issued_at": NOW - timedelta(hours=2),
            "expires_at": NOW - timedelta(hours=1),
        }
    )
    receipt_path = (
        fixture["receipt_root"] / "machine-policy" / fixture["work_item_id"] / f"{SHA}.json"
    )
    receipt_path.write_bytes(expired.canonical_json_bytes())
    fixture["authority"] = RuntimeAuthority(expired, fixture["activation"])
    with pytest.raises(NativeValueRuntimeError, match="expired"):
        load_authorized_native_value_transition(**runtime_arguments(fixture))


def test_controller_orders_independent_value_authority_before_handoff_and_publication() -> None:
    source = (Path(__file__).parents[1] / "tcfactory/v3/controller.py").read_text(
        encoding="utf-8"
    )
    source = source[source.index("async def _execute") :]
    manifest_binding = source.index("manifest.verify_artifacts")
    authority_load = source.index("load_authorized_native_value_transition")
    handoff = source.index("write_v3_handoff", authority_load)
    publication = source.index("self.publisher.publish", handoff)
    assert manifest_binding < authority_load < handoff < publication
    assert "WorkKind.CONTROLLED_EXPERIMENT" in source
    assert "WorkStatus.BLOCKED_POLICY" in source


def test_machine_policy_review_binds_exact_context_evidence_and_live_activation() -> None:
    class BoundAuthority:
        def __init__(
            self,
            bound_receipt: MachinePolicyReceiptV31,
            bound_activation: ActivationReceiptV31,
        ) -> None:
            self.receipt = bound_receipt
            self.activation = bound_activation

        def verify_machine_receipt(self, receipt_path: Path, **expected: object):
            del receipt_path
            for field, value in expected.items():
                if getattr(self.receipt, field) != value:
                    raise NativeValueRuntimeError(f"receipt {field} mismatch")
            return self.receipt

        def verify_activation(self, activation_path: Path, **expected: object):
            del activation_path
            fields = {
                "expected_main_sha": "verified_main_sha",
                "source_generation_id": "source_generation_id",
                "source_generation_digest": "source_generation_digest",
                "controller_binary_digest": "controller_binary_digest",
                "controller_config_digest": "controller_config_digest",
            }
            for requested, field in fields.items():
                if getattr(self.activation, field) != expected[requested]:
                    raise NativeValueRuntimeError(f"activation {field} mismatch")
            return self.activation

    item = benchmark(freshness())
    context = DIGEST_OTHER
    dependency = DIGEST_NATIVE
    receipt = machine_receipt(
        item,
        DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED,
        work_item_id="V3-PROD-001",
        milestone_id="M1_PRODUCT_WEDGE",
        lane=Lane.PRODUCT,
        risk_tier=RiskTier.STANDARD,
        candidate_sha=SHA,
        candidate_tree_sha=TREE,
        base_sha=BASE,
        request_digest=context,
        source_generation_id="source:v31",
        source_generation_digest=DIGEST_OTHER,
        context_manifest_digest=context,
        task_packet_digest=context,
        candidate_manifest_digest=DIGEST_TC,
        checkpoint_digest=context,
        required_gate_results={"V3-PROD-000": GateResult.PASS},
        raw_evidence_artifact_hashes=[dependency],
    )
    activation = ActivationReceiptV31(
        schema_version="3.1",
        receipt_id="ACTIVATION:REVIEW:001",
        verified_main_sha=SHA,
        machine_environment_digest=DIGEST_OTHER,
        source_generation_id="source:v31",
        source_generation_digest=DIGEST_OTHER,
        controller_binary_digest=DIGEST_OTHER,
        controller_config_digest=DIGEST_OTHER,
        machine_environment_path="runtime/machine-environment.json",
        controller_binary_path="tcfactory/v3/controller.py",
        controller_config_path="config/factory.yaml",
        machine_policy_receipt_id=receipt.receipt_id,
        machine_policy_receipt_digest=receipt.canonical_digest(),
        mode=ActivationMode.LIVE,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=55),
        revocation_epoch=1,
        nonce="review-activation-0123456789",
        issuer_id="VERIFIER:LOCAL:001",
        issuer_key_id="KEY:ED25519:001",
        signature_algorithm="ed25519",
        signature="3" * 96,
    )
    authorized = load_authorized_machine_policy_review(
        receipt_path=Path("receipt.json"),
        activation_path=Path("activation.json"),
        authority=BoundAuthority(receipt, activation),
        work_item_id="V3-PROD-001",
        milestone_id="M1_PRODUCT_WEDGE",
        lane=Lane.PRODUCT,
        risk_tier=RiskTier.STANDARD,
        candidate_sha=SHA,
        candidate_tree_sha=TREE,
        base_sha=BASE,
        candidate_manifest_digest=DIGEST_TC,
        review_context_digest=context,
        dependency_evidence_digests=[dependency],
        required_gate_results={"V3-PROD-000": GateResult.PASS},
        expected_main_sha=SHA,
        source_generation_id="source:v31",
        source_generation_digest=DIGEST_OTHER,
        controller_binary_digest=DIGEST_OTHER,
        controller_config_digest=DIGEST_OTHER,
        now=NOW,
    )
    assert authorized.resulting_status is WorkStatus.PASSED_ENGINEERING
    assert authorized.machine_receipt_digest == receipt.canonical_digest()

    for update, message in (
        ({"work_item_id": "V3-PROD-002"}, "receipt was rejected"),
        ({"candidate_sha": "f" * 40}, "receipt was rejected"),
        ({"request_digest": DIGEST_TC}, "request_digest mismatch"),
        ({"raw_evidence_artifact_hashes": [DIGEST_TC]}, "evidence roster mismatch"),
    ):
        forged = receipt.model_copy(update=update)
        with pytest.raises((MachinePolicyRuntimeError, NativeValueRuntimeError), match=message):
            load_authorized_machine_policy_review(
                receipt_path=Path("receipt.json"),
                activation_path=Path("activation.json"),
                authority=BoundAuthority(forged, activation),
                work_item_id="V3-PROD-001",
                milestone_id="M1_PRODUCT_WEDGE",
                lane=Lane.PRODUCT,
                risk_tier=RiskTier.STANDARD,
                candidate_sha=SHA,
                candidate_tree_sha=TREE,
                base_sha=BASE,
                candidate_manifest_digest=DIGEST_TC,
                review_context_digest=context,
                dependency_evidence_digests=[dependency],
                required_gate_results={"V3-PROD-000": GateResult.PASS},
                expected_main_sha=SHA,
        source_generation_id="source:v31",
                source_generation_digest=DIGEST_OTHER,
                controller_binary_digest=DIGEST_OTHER,
                controller_config_digest=DIGEST_OTHER,
                now=NOW,
            )

    stale_activation = activation.model_copy(update={"mode": ActivationMode.CANARY})
    with pytest.raises(MachinePolicyRuntimeError, match="LIVE activation"):
        load_authorized_machine_policy_review(
            receipt_path=Path("receipt.json"),
            activation_path=Path("activation.json"),
            authority=BoundAuthority(receipt, stale_activation),
            work_item_id="V3-PROD-001",
            milestone_id="M1_PRODUCT_WEDGE",
            lane=Lane.PRODUCT,
            risk_tier=RiskTier.STANDARD,
            candidate_sha=SHA,
            candidate_tree_sha=TREE,
            base_sha=BASE,
            candidate_manifest_digest=DIGEST_TC,
            review_context_digest=context,
            dependency_evidence_digests=[dependency],
            required_gate_results={"V3-PROD-000": GateResult.PASS},
            expected_main_sha=SHA,
        source_generation_id="source:v31",
            source_generation_digest=DIGEST_OTHER,
            controller_binary_digest=DIGEST_OTHER,
            controller_config_digest=DIGEST_OTHER,
            now=NOW,
        )
