from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import scripts.generate_v31_contract_schemas as schema_generator
from scripts.generate_v31_contract_schemas import SCHEMA_ROOT, rendered_schemas
from tcfactory.v3.contracts_v31 import (
    ActivationMode,
    ActivationReceiptV31,
    CommercialState,
    DecisionValueDisposition,
    DecisionValueResultV31,
    EpistemicState,
    EvidenceMode,
    ExecutionOutcome,
    ExecutionReportV31,
    FingerprintCounterV31,
    FingerprintDisposition,
    FreshnessState,
    GateResult,
    MachinePolicyReceiptV31,
    MachinePolicyRevocationListV31,
    MilestoneCompletionProposalV31,
    NativeSubstituteBenchmarkV31,
    NativeSubstituteDisposition,
    OutputDeclarationV31,
    OutputKind,
    PolicyDecision,
    PRPublicationPhase,
    PRPublicationTransactionV31,
    ReleaseState,
    RuntimeEventKind,
    RuntimeEventV31,
    RuntimeMode,
    RuntimeStatusV31,
    SessionReferenceV31,
    SessionState,
    SourceFreshnessReceiptV31,
    SourceGenerationV31,
    TechnicalState,
    ValueState,
    migrate_v3_contract,
    validate_v31_contract,
)
from tcfactory.v3.enums import Lane, RiskTier

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SHA = "a" * 40
SHA_B = "b" * 40
SIGNATURE = "A" * 64


def _source_generation() -> SourceGenerationV31:
    return SourceGenerationV31(
        schema_version="3.1",
        generation_id="V3.1-ZH-2026-08-12",
        manifest_digest=DIGEST,
        source_digests={"docs/spec.md": DIGEST},
        active_normative=True,
        supersedes_generation_id="V3-2026-08-11",
        created_at=NOW,
    )


def _output() -> OutputDeclarationV31:
    return OutputDeclarationV31(
        schema_version="3.1",
        output_id="OUTPUT:REPORT:001",
        path="factory/evidence/report.json",
        kind=OutputKind.REPORT,
        media_type="application/json",
        required=True,
        maximum_bytes=4096,
        content_digest=DIGEST,
        producer_work_item_id="V3-PROD-001",
        retention_days=30,
    )


def _session() -> SessionReferenceV31:
    return SessionReferenceV31(
        schema_version="3.1",
        session_id="SESSION:TEST:001",
        work_item_id="V3-PROD-001",
        provider="controlled",
        backend="fake",
        task_packet_digest=DIGEST,
        state=SessionState.COMPLETED,
        started_at=NOW,
        ended_at=NOW + timedelta(minutes=1),
        transcript_digest=DIGEST_B,
    )


def _policy_receipt(**updates: Any) -> MachinePolicyReceiptV31:
    payload: dict[str, Any] = {
        "schema_version": "3.1",
        "receipt_id": "RECEIPT:POLICY:001",
        "policy_id": "POLICY:ZERO-HUMAN",
        "policy_version": "3.1.0",
        "issuer_id": "VERIFIER:LOCAL:001",
        "issuer_key_id": "KEY:ED25519:001",
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
        "revocation_epoch": 1,
        "nonce": "0123456789abcdef",
        "request_digest": DIGEST,
        "work_item_id": "V3-PROD-001",
        "milestone_id": "M1_PRODUCT_WEDGE",
        "lane": Lane.PRODUCT,
        "risk_tier": RiskTier.TRUST_CORE,
        "candidate_sha": SHA,
        "candidate_tree_sha": SHA_B,
        "base_sha": "c" * 40,
        "source_generation_id": "V3.1-ZH-2026-08-12",
        "source_generation_digest": DIGEST,
        "context_manifest_digest": DIGEST,
        "task_packet_digest": DIGEST,
        "candidate_manifest_digest": DIGEST,
        "checkpoint_digest": DIGEST,
        "required_gate_results": {"FACTORY-QUALITY": GateResult.PASS},
        "private_gate_suite_id": "FULL-RELEASE-V31",
        "private_gate_runner_digest": DIGEST,
        "independent_oracle_ids": ["ORACLE:CONFORMANCE:001"],
        "raw_evidence_artifact_hashes": [DIGEST_B],
        "native_substitute_disposition": NativeSubstituteDisposition.INCREMENTAL_VALUE,
        "decision_value_disposition": (
            DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        ),
        "engineering_maturity_ceiling": TechnicalState.PASSED,
        "commercial_maturity_ceiling": CommercialState.PILOT_ELIGIBLE,
        "allowed_claims": ["CLAIM:ENGINEERING-PASS"],
        "forbidden_claims": ["CLAIM:COMMERCIAL-SUPPORT"],
        "publication_scope": ["packages/traincapsule-core/**"],
        "decision": PolicyDecision.PASS,
        "signature_algorithm": "ed25519",
        "signature": SIGNATURE,
    }
    payload.update(updates)
    return MachinePolicyReceiptV31.model_validate(payload, strict=True)


def test_all_native_v31_contracts_accept_coherent_records() -> None:
    source = _source_generation()
    freshness = SourceFreshnessReceiptV31(
        schema_version="3.1",
        receipt_id="RECEIPT:FRESHNESS:001",
        generation_id=source.generation_id,
        generation_digest=source.manifest_digest,
        source_id="SOURCE:PYTORCH:001",
        source_digest=DIGEST,
        observed_at=NOW,
        expires_at=NOW + timedelta(days=7),
        state=FreshnessState.FRESH,
        issuer_id="VERIFIER:SOURCE:001",
        issuer_key_id="KEY:SOURCE:001",
        signature_algorithm="ed25519",
        signature=SIGNATURE,
    )
    execution = ExecutionReportV31(
        schema_version="3.1",
        execution_id="EXECUTION:TEST:001",
        session=_session(),
        evidence_mode=EvidenceMode.CONTROLLED_VALIDATED,
        command_digest=DIGEST,
        started_at=NOW,
        finished_at=NOW + timedelta(minutes=1),
        exit_code=0,
        outcome=ExecutionOutcome.PASS,
        attempt=1,
        maximum_attempts=2,
        stdout_artifact_digest=DIGEST,
        stderr_artifact_digest=DIGEST_B,
        outputs=[_output()],
    )
    counter = FingerprintCounterV31(
        schema_version="3.1",
        fingerprint=DIGEST,
        count=2,
        maximum_occurrences=3,
        disposition=FingerprintDisposition.REPEATED,
        first_seen_at=NOW,
        last_seen_at=NOW + timedelta(minutes=1),
    )
    benchmark = NativeSubstituteBenchmarkV31(
        schema_version="3.1",
        benchmark_id="BENCHMARK:NATIVE:001",
        work_item_id="V3-PROD-001",
        candidate_sha=SHA,
        candidate_tree_sha=SHA_B,
        baseline_environment_digest=DIGEST,
        candidate_environment_digest=DIGEST_B,
        native_tool="PyTorch Flight Recorder",
        native_tool_version="2.5.1",
        native_evidence_digests=[DIGEST],
        candidate_evidence_digests=[DIGEST_B],
        independent_oracle_ids=["ORACLE:NATIVE:001"],
        native_effort_minutes=30.0,
        candidate_effort_minutes=10.0,
        decision_changed=True,
        disposition=NativeSubstituteDisposition.INCREMENTAL_VALUE,
    )
    value = DecisionValueResultV31(
        schema_version="3.1",
        work_item_id="V3-PROD-001",
        evaluated=True,
        disposition=DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED,
        native_benchmark_digest=benchmark.canonical_digest(),
        evidence_refs=[DIGEST],
        original_experiment_cost=100.0,
        proposed_experiment_cost=25.0,
        original_experiment_minutes=60.0,
        proposed_experiment_minutes=15.0,
        decision_changed=True,
        rationale="The candidate changed the bounded operational decision.",
        value_state=ValueState.INCREMENTAL_VALUE,
    )
    policy = _policy_receipt()
    revocations = MachinePolicyRevocationListV31(
        schema_version="3.1",
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        revocation_epoch=1,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=7),
        signature_algorithm="ed25519",
        signature=SIGNATURE,
    )
    activation = ActivationReceiptV31(
        schema_version="3.1",
        receipt_id="RECEIPT:ACTIVATION:001",
        verified_main_sha=SHA,
        machine_environment_digest=DIGEST,
        source_generation_id=source.generation_id,
        source_generation_digest=source.manifest_digest,
        controller_binary_digest=DIGEST,
        controller_config_digest=DIGEST_B,
        machine_policy_receipt_id=policy.receipt_id,
        machine_policy_receipt_digest=policy.canonical_digest(),
        mode=ActivationMode.CANARY,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revocation_epoch=1,
        nonce="activation-nonce-001",
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        signature_algorithm="ed25519",
        signature=SIGNATURE,
    )
    publication = PRPublicationTransactionV31(
        schema_version="3.1",
        transaction_id="PUBLICATION:PR:001",
        work_item_id="V3-PROD-001",
        candidate_branch="codex/v31-contracts",
        base_sha="c" * 40,
        candidate_sha=SHA,
        candidate_tree_sha=SHA_B,
        pull_request_number=1,
        pull_request_url="https://github.com/TasfiqJ/TrainCapsule/pull/1",
        machine_policy_receipt_id=policy.receipt_id,
        machine_policy_receipt_digest=policy.canonical_digest(),
        phase=PRPublicationPhase.READY_TO_MERGE,
        attempt=1,
        maximum_attempts=3,
        automated_merge=True,
        required_human_approvals=0,
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=1),
    )
    proposal = MilestoneCompletionProposalV31(
        schema_version="3.1",
        proposal_id="PROPOSAL:MILESTONE:001",
        milestone_id="M1_PRODUCT_WEDGE",
        candidate_sha=SHA,
        work_item_ids=["V3-PROD-001"],
        completion_evidence_digests=[DIGEST],
        technical_state=TechnicalState.PASSED,
        epistemic_state=EpistemicState.CONTROLLED,
        value_state=ValueState.INCREMENTAL_VALUE,
        release_state=ReleaseState.AUTHORIZED,
        commercial_state=CommercialState.NATIVE_ADVANTAGE_UNPROVEN,
        machine_policy_receipt_id=policy.receipt_id,
        machine_policy_receipt_digest=policy.canonical_digest(),
        proposed_at=NOW,
    )
    status = RuntimeStatusV31(
        schema_version="3.1",
        snapshot_id="RUNTIME:SNAPSHOT:001",
        observed_at=NOW,
        mode=RuntimeMode.CANARY,
        autonomy_enabled=True,
        activation_receipt_id=activation.receipt_id,
        activation_receipt_digest=activation.canonical_digest(),
        source_generation_id=source.generation_id,
        source_generation_digest=source.manifest_digest,
        controller_binary_digest=DIGEST,
        controller_config_digest=DIGEST_B,
        current_work_item_id="V3-PROD-001",
        technical_state=TechnicalState.PASSED,
        epistemic_state=EpistemicState.CONTROLLED,
        value_state=ValueState.INCREMENTAL_VALUE,
        release_state=ReleaseState.AUTHORIZED,
        commercial_state=CommercialState.NATIVE_ADVANTAGE_UNPROVEN,
        queued_count=0,
        blocked_count=0,
    )
    event = RuntimeEventV31(
        schema_version="3.1",
        event_id="RUNTIME:EVENT:001",
        sequence=1,
        occurred_at=NOW,
        kind=RuntimeEventKind.STARTED,
        mode=RuntimeMode.CANARY,
        work_item_id="V3-PROD-001",
        current_state="RUNNING",
        evidence_digests=[activation.canonical_digest()],
        reason="Bounded canary started under a signed activation receipt.",
    )
    records = [
        source,
        freshness,
        _output(),
        _session(),
        execution,
        counter,
        benchmark,
        value,
        policy,
        revocations,
        activation,
        publication,
        proposal,
        status,
        event,
    ]
    assert len(records) == 15
    assert all(record.schema_version == "3.1" for record in records)


@pytest.mark.parametrize("bad_schema_version", [None, "3", "3.1.0", 3.1])
def test_schema_version_is_explicit_and_exact(bad_schema_version: object) -> None:
    payload = _source_generation().model_dump(mode="python", by_alias=True)
    if bad_schema_version is None:
        payload.pop("schemaVersion")
    else:
        payload["schemaVersion"] = bad_schema_version
    with pytest.raises(ValidationError):
        SourceGenerationV31.model_validate(payload, strict=True)


def test_unknown_fields_and_non_normalized_paths_are_rejected() -> None:
    payload = _output().model_dump(mode="python", by_alias=True)
    payload["callerVerdict"] = "PASS"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OutputDeclarationV31.model_validate(payload, strict=True)
    for path in ("../escape", "safe/../escape", "/absolute", "windows\\escape"):
        payload = _output().model_dump(mode="python", by_alias=True)
        payload["path"] = path
        with pytest.raises(ValidationError):
            OutputDeclarationV31.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("model", "payload", "field", "value"),
    [
        (ExecutionReportV31, lambda: _execution_payload(), "attempt", 0),
        (ExecutionReportV31, lambda: _execution_payload(), "maximumAttempts", 0),
        (FingerprintCounterV31, lambda: _counter_payload(), "count", 0),
        (FingerprintCounterV31, lambda: _counter_payload(), "maximumOccurrences", 0),
        (PRPublicationTransactionV31, lambda: _publication_payload(), "attempt", 0),
        (PRPublicationTransactionV31, lambda: _publication_payload(), "maximumAttempts", 0),
    ],
)
def test_zero_never_means_unbounded(model: type[Any], payload: Any, field: str, value: int) -> None:
    raw = payload()
    raw[field] = value
    with pytest.raises(ValidationError):
        model.model_validate(raw, strict=True)


def _execution_payload() -> dict[str, Any]:
    return ExecutionReportV31(
        schema_version="3.1",
        execution_id="EXECUTION:TEST:002",
        session=_session(),
        evidence_mode=EvidenceMode.CONTROLLED_VALIDATED,
        command_digest=DIGEST,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=1),
        exit_code=0,
        outcome=ExecutionOutcome.PASS,
        attempt=1,
        maximum_attempts=2,
        stdout_artifact_digest=DIGEST,
        stderr_artifact_digest=DIGEST_B,
    ).model_dump(mode="python", by_alias=True)


def _counter_payload() -> dict[str, Any]:
    return FingerprintCounterV31(
        schema_version="3.1",
        fingerprint=DIGEST,
        count=1,
        maximum_occurrences=3,
        disposition=FingerprintDisposition.NEW,
        first_seen_at=NOW,
        last_seen_at=NOW,
    ).model_dump(mode="python", by_alias=True)


def _publication_payload() -> dict[str, Any]:
    return PRPublicationTransactionV31(
        schema_version="3.1",
        transaction_id="PUBLICATION:PR:002",
        work_item_id="V3-PROD-001",
        candidate_branch="codex/v31-contracts",
        base_sha=SHA_B,
        candidate_sha=SHA,
        candidate_tree_sha=SHA_B,
        machine_policy_receipt_id="RECEIPT:POLICY:001",
        machine_policy_receipt_digest=DIGEST,
        phase=PRPublicationPhase.PREPARED,
        attempt=1,
        maximum_attempts=3,
        automated_merge=True,
        required_human_approvals=0,
        created_at=NOW,
        updated_at=NOW,
    ).model_dump(mode="python", by_alias=True)


def test_policy_receipt_fails_closed_for_bad_gate_expiry_and_claim_laundering() -> None:
    with pytest.raises(ValidationError, match="every named gate"):
        _policy_receipt(required_gate_results={"FACTORY-QUALITY": GateResult.UNKNOWN})
    with pytest.raises(ValidationError, match="expiry"):
        _policy_receipt(expires_at=NOW)
    with pytest.raises(ValidationError, match="overlap"):
        _policy_receipt(
            allowed_claims=["CLAIM:SAME"],
            forbidden_claims=["CLAIM:SAME"],
        )
    with pytest.raises(ValidationError, match="incremental decision value"):
        _policy_receipt(
            commercial_maturity_ceiling=CommercialState.COMMERCIALLY_SUPPORTED,
            decision_value_disposition=DecisionValueDisposition.UNKNOWN,
        )
    with pytest.raises(ValidationError, match="normalized repository-relative"):
        _policy_receipt(publication_scope=["../authority"])


def test_stale_freshness_cannot_omit_conflict_or_wedge_evidence() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "3.1",
        "receiptId": "RECEIPT:FRESHNESS:002",
        "generationId": "V3.1-ZH-2026-08-12",
        "generationDigest": DIGEST,
        "sourceId": "SOURCE:PYTORCH:001",
        "sourceDigest": DIGEST,
        "observedAt": NOW,
        "expiresAt": NOW + timedelta(days=7),
        "state": FreshnessState.STALE,
        "issuerId": "VERIFIER:SOURCE:001",
        "issuerKeyId": "KEY:SOURCE:001",
        "signatureAlgorithm": "ed25519",
        "signature": SIGNATURE,
    }
    with pytest.raises(ValidationError, match="conflict evidence"):
        SourceFreshnessReceiptV31.model_validate(payload, strict=True)
    payload["conflictArtifactDigests"] = [DIGEST]
    payload["wedgeWorkItemId"] = "V3-MKT-001"
    assert (
        SourceFreshnessReceiptV31.model_validate(payload, strict=True).state is FreshnessState.STALE
    )


def test_session_and_execution_terminal_claims_are_derived_not_caller_asserted() -> None:
    session = _session().model_dump(mode="python", by_alias=True)
    session["state"] = SessionState.RUNNING
    with pytest.raises(ValidationError, match="terminal session"):
        SessionReferenceV31.model_validate(session, strict=True)

    execution = _execution_payload()
    execution["exitCode"] = 1
    with pytest.raises(ValidationError, match="disagree"):
        ExecutionReportV31.model_validate(execution, strict=True)
    execution = _execution_payload()
    execution["attempt"] = 3
    with pytest.raises(ValidationError, match="exceeds"):
        ExecutionReportV31.model_validate(execution, strict=True)


def test_fingerprint_and_native_value_states_cannot_be_laundered() -> None:
    counter = _counter_payload()
    counter["count"] = 2
    with pytest.raises(ValidationError, match="disagrees"):
        FingerprintCounterV31.model_validate(counter, strict=True)

    benchmark = {
        "schemaVersion": "3.1",
        "benchmarkId": "BENCHMARK:NATIVE:002",
        "workItemId": "V3-PROD-001",
        "candidateSha": SHA,
        "candidateTreeSha": SHA_B,
        "baselineEnvironmentDigest": DIGEST,
        "candidateEnvironmentDigest": DIGEST_B,
        "nativeTool": "PyTorch Flight Recorder",
        "nativeToolVersion": "2.5.1",
        "nativeEvidenceDigests": [DIGEST],
        "candidateEvidenceDigests": [DIGEST_B],
        "independentOracleIds": ["ORACLE:NATIVE:001"],
        "nativeEffortMinutes": 30.0,
        "candidateEffortMinutes": 10.0,
        "decisionChanged": False,
        "disposition": NativeSubstituteDisposition.INCREMENTAL_VALUE,
    }
    with pytest.raises(ValidationError, match="changed operational decision"):
        NativeSubstituteBenchmarkV31.model_validate(benchmark, strict=True)


def test_revocation_activation_publication_and_maturity_boundaries_fail_closed() -> None:
    revocations = {
        "schemaVersion": "3.1",
        "policyId": "POLICY:ZERO-HUMAN",
        "policyVersion": "3.1.0",
        "issuerId": "VERIFIER:LOCAL:001",
        "issuerKeyId": "KEY:ED25519:001",
        "revocationEpoch": 1,
        "issuedAt": NOW,
        "expiresAt": NOW + timedelta(days=1),
        "revokedNonces": ["same-nonce", "same-nonce"],
        "signatureAlgorithm": "ed25519",
        "signature": SIGNATURE,
    }
    with pytest.raises(ValidationError, match="revoked nonces must be unique"):
        MachinePolicyRevocationListV31.model_validate(revocations, strict=True)

    activation = {
        "schemaVersion": "3.1",
        "receiptId": "RECEIPT:ACTIVATION:002",
        "verifiedMainSha": SHA,
        "machineEnvironmentDigest": DIGEST,
        "sourceGenerationId": "V3.1-ZH-2026-08-12",
        "sourceGenerationDigest": DIGEST,
        "controllerBinaryDigest": DIGEST,
        "controllerConfigDigest": DIGEST,
        "machinePolicyReceiptId": "RECEIPT:POLICY:001",
        "machinePolicyReceiptDigest": DIGEST,
        "mode": ActivationMode.LIVE,
        "issuedAt": NOW,
        "expiresAt": NOW,
        "revocationEpoch": 1,
        "nonce": "activation-nonce-002",
        "issuerId": "VERIFIER:LOCAL:001",
        "issuerKeyId": "KEY:ED25519:001",
        "signatureAlgorithm": "ed25519",
        "signature": SIGNATURE,
    }
    with pytest.raises(ValidationError, match="expiry"):
        ActivationReceiptV31.model_validate(activation, strict=True)

    publication = _publication_payload()
    publication["phase"] = PRPublicationPhase.READY_TO_MERGE
    with pytest.raises(ValidationError, match="number and URL"):
        PRPublicationTransactionV31.model_validate(publication, strict=True)

    proposal = {
        "schemaVersion": "3.1",
        "proposalId": "PROPOSAL:MILESTONE:002",
        "milestoneId": "M1_PRODUCT_WEDGE",
        "candidateSha": SHA,
        "workItemIds": ["V3-PROD-001"],
        "completionEvidenceDigests": [DIGEST],
        "technicalState": TechnicalState.PASSED,
        "epistemicState": EpistemicState.CONTROLLED,
        "valueState": ValueState.INCREMENTAL_VALUE,
        "releaseState": ReleaseState.AUTHORIZED,
        "commercialState": CommercialState.COMMERCIALLY_SUPPORTED,
        "machinePolicyReceiptId": "RECEIPT:POLICY:001",
        "machinePolicyReceiptDigest": DIGEST,
        "proposedAt": NOW,
    }
    with pytest.raises(ValidationError, match="external verified evidence"):
        MilestoneCompletionProposalV31.model_validate(proposal, strict=True)


def test_runtime_live_mode_requires_activation_and_autonomy() -> None:
    base = {
        "schemaVersion": "3.1",
        "snapshotId": "RUNTIME:SNAPSHOT:002",
        "observedAt": NOW,
        "mode": RuntimeMode.LIVE,
        "autonomyEnabled": False,
        "sourceGenerationId": "V3.1-ZH-2026-08-12",
        "sourceGenerationDigest": DIGEST,
        "controllerBinaryDigest": DIGEST,
        "controllerConfigDigest": DIGEST,
        "technicalState": TechnicalState.NOT_EVALUATED,
        "epistemicState": EpistemicState.UNKNOWN,
        "valueState": ValueState.NOT_EVALUATED,
        "releaseState": ReleaseState.NOT_REQUESTED,
        "commercialState": CommercialState.NOT_EVALUATED,
        "queuedCount": 0,
        "blockedCount": 0,
    }
    with pytest.raises(ValidationError, match="activation receipt"):
        RuntimeStatusV31.model_validate(base, strict=True)


def test_migration_is_explicit_lossless_and_does_not_invent_v31_authority() -> None:
    legacy = {
        "findingId": "FIND-LEGACY-001",
        "summary": "V3 finding preserved without authority upgrade",
        "advisory": False,
    }
    migrated = migrate_v3_contract("finding", legacy)
    assert migrated.schema_version == "3.1"
    assert migrated.migrated_from_schema_version == "3"
    assert migrated.payload.model_dump(mode="json", by_alias=True) == {
        **legacy,
        "artifactPath": None,
        "artifactDigest": None,
        "declaredOwner": None,
    }
    with pytest.raises(ValidationError):
        migrate_v3_contract("finding", {**legacy, "callerPass": True})
    with pytest.raises(ValueError, match="unsupported"):
        migrate_v3_contract("machine-policy-receipt", legacy)


def test_registry_validation_rejects_unregistered_and_missing_schema_version() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        validate_v31_contract("made-up-contract", {})
    payload = _output().model_dump(mode="python", by_alias=True)
    payload.pop("schemaVersion")
    with pytest.raises(ValidationError):
        validate_v31_contract("output-declaration", payload)


def test_committed_v31_schemas_are_current_closed_and_lf_only() -> None:
    expected = rendered_schemas()
    observed = {path.name for path in SCHEMA_ROOT.glob("*.schema.json")}
    assert observed == set(expected)
    for name, content in expected.items():
        raw = (SCHEMA_ROOT / name).read_bytes()
        assert raw == content.encode("utf-8")
        assert b"\r" not in raw
        schema = json.loads(raw)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        assert "schemaVersion" in schema["required"]
        assert schema["properties"]["schemaVersion"]["const"] == "3.1"


def test_schema_check_rejects_crlf_or_other_byte_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = rendered_schemas()
    for name, content in expected.items():
        (tmp_path / name).write_bytes(content.encode("utf-8"))
    first_name = sorted(expected)[0]
    (tmp_path / first_name).write_bytes(expected[first_name].replace("\n", "\r\n").encode())
    monkeypatch.setattr(schema_generator, "SCHEMA_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["generate_v31_contract_schemas.py", "--check"])
    with pytest.raises(SystemExit, match="stale"):
        schema_generator.main()
