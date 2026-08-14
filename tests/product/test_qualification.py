from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from traincapsule_core import (
    LocalEvidenceStore,
    build_environment_identity,
    build_workload_identity,
    digest_json,
    sha256_digest,
)
from traincapsule_core.models import (
    CaseEconomics,
    CompletenessState,
    EligibilityOutcome,
    EvidenceArtifact,
    EvidenceIntegrity,
    EvidenceRole,
    ExperimentEconomics,
    FindingAttribution,
    IdentityStrength,
    IncidentCase,
    NativeFinding,
    OperationalDecision,
    PrivacyClass,
    TechnicalResult,
)
from traincapsule_ingest_pytorch import reimport_from_raw_artifacts
from traincapsule_qualify import (
    CommandExpectation,
    ExperimentSpecification,
    NativeBaseline,
    PreflightInputs,
    QualificationResult,
    assess_completeness,
    evaluate_preflight,
    execute_qualification,
    generate_native_baseline,
    render_native_baseline_human,
)

from .test_identity import environment_material, workload_material


def test_zero_human_outcome_vocabulary_has_no_intervention_state() -> None:
    assert "ELIGIBLE_WITH_HUMAN_REVIEW" not in EligibilityOutcome.__members__


RAW = (
    b'{"entries":[{"collective_seq_id":42,"profiling_name":"nccl:all_reduce",'
    b'"state":"completed"}],"pg_id":"0","pytorch_version":"2.5.1","rank":0,'
    b'"version":"2.5","world_size":2}'
)
RAW_COMPLETED = (
    b'{"entries":[{"collective_seq_id":42,"profiling_name":"nccl:all_reduce",'
    b'"state":"completed"}],"pg_id":"0","pytorch_version":"2.5.1","rank":1,'
    b'"version":"2.5","world_size":2}'
)
RAW_STARTED = (
    b'{"entries":[{"collective_seq_id":42,"profiling_name":"nccl:all_reduce",'
    b'"state":"started"}],"pg_id":"0","pytorch_version":"2.5.1","rank":1,'
    b'"version":"2.5","world_size":2}'
)
RAW_OMITTED = (
    b'{"entries":[],"pg_id":"0","pytorch_version":"2.5.1","rank":1,'
    b'"version":"2.5","world_size":2}'
)
DIGEST = sha256_digest(RAW)
EVALUATED_AT = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
DEADLINE = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
WORKLOAD = build_workload_identity(workload_material())
BASELINE_RECIPE = b"baseline-materialization-v1"
CANDIDATE_RECIPE = b"candidate-materialization-v1"
_baseline_material = environment_material()
_baseline_material["materializationRecipeDigest"] = sha256_digest(BASELINE_RECIPE)
BASELINE_ENVIRONMENT = build_environment_identity(_baseline_material)
_candidate_material = environment_material()
_candidate_material["scheduler"] = "local"
_candidate_material["materializationRecipeDigest"] = sha256_digest(CANDIDATE_RECIPE)
CANDIDATE_ENVIRONMENT = build_environment_identity(_candidate_material)
assert BASELINE_ENVIRONMENT.materialization_recipe_digest is not None
assert CANDIDATE_ENVIRONMENT.materialization_recipe_digest is not None
PAYLOADS = {
    sha256_digest(RAW): RAW,
    sha256_digest(RAW_COMPLETED): RAW_COMPLETED,
    sha256_digest(RAW_STARTED): RAW_STARTED,
    sha256_digest(RAW_OMITTED): RAW_OMITTED,
    sha256_digest(BASELINE_RECIPE): BASELINE_RECIPE,
    sha256_digest(CANDIDATE_RECIPE): CANDIDATE_RECIPE,
}


def binding_artifact(*, baseline: bool) -> EvidenceArtifact:
    payload = BASELINE_RECIPE if baseline else CANDIDATE_RECIPE
    kind = (
        "BASELINE_MATERIALIZATION_RECIPE"
        if baseline
        else "CANDIDATE_MATERIALIZATION_RECIPE"
    )
    digest = sha256_digest(payload)
    raw: dict[str, object] = {
        "schemaVersion": 1,
        "artifactId": digest,
        "caseId": "CASE-QUALIFY",
        "workloadId": WORKLOAD.workload_id,
        "baselineEnvironmentId": BASELINE_ENVIRONMENT.environment_id,
        "candidateEnvironmentId": CANDIDATE_ENVIRONMENT.environment_id,
        "kind": kind,
        "sourceAdapter": "traincapsule-materialization-recipe",
        "sourceVersion": "1",
        "capturedAt": "2026-08-11T20:00:00Z",
        "contentDigest": digest,
        "sizeBytes": len(payload),
        "compression": "none",
        "encryption": "none",
        "privacyClass": PrivacyClass.CONFIDENTIAL.value,
        "customerLocalUri": f"cas://CASE-QUALIFY/sha256/{digest.removeprefix('sha256:')}",
        "exportPolicy": "LOCAL_ONLY",
        "provenance": {},
        "integrityStatus": EvidenceIntegrity.VALID.value,
    }
    raw["metadataDigest"] = digest_json(raw)
    return EvidenceArtifact.model_validate(raw)


def artifact(
    case_id: str = "CASE-QUALIFY", *, payload: bytes = RAW, rank: int = 0
) -> EvidenceArtifact:
    digest = sha256_digest(payload)
    raw: dict[str, object] = {
        "schemaVersion": 1,
        "artifactId": digest,
        "caseId": case_id,
        "workloadId": WORKLOAD.workload_id,
        "baselineEnvironmentId": BASELINE_ENVIRONMENT.environment_id,
        "candidateEnvironmentId": CANDIDATE_ENVIRONMENT.environment_id,
        "kind": "PYTORCH_FLIGHT_RECORDER_RAW",
        "sourceAdapter": "pytorch-flight-recorder",
        "sourceVersion": "RAW_UNPARSED",
        "capturedAt": "2026-08-11T20:00:00Z",
        "contentDigest": digest,
        "sizeBytes": len(payload),
        "compression": "none",
        "encryption": "none",
        "privacyClass": PrivacyClass.CONFIDENTIAL.value,
        "customerLocalUri": f"cas://{case_id}/sha256/{digest.removeprefix('sha256:')}",
        "exportPolicy": "LOCAL_ONLY",
        "provenance": {"sourceRelativePath": f"rank-{rank}.json"},
        "integrityStatus": EvidenceIntegrity.VALID.value,
    }
    raw["metadataDigest"] = digest_json(raw)
    return EvidenceArtifact.model_validate(raw)


def native_finding(evidence_refs: list[str] | None = None) -> NativeFinding:
    artifacts = [artifact(), artifact(payload=RAW_COMPLETED, rank=1)]
    imported = reimport_from_raw_artifacts(
        artifacts,
        lambda item: PAYLOADS[item.content_digest],
        binding_artifacts=[binding_artifact(baseline=True), binding_artifact(baseline=False)],
    )
    finding = imported.native_findings[0]
    if evidence_refs is not None and evidence_refs != finding.evidence_refs:
        return finding.model_copy(update={"evidence_refs": evidence_refs})
    return finding


def native_baseline(*, decision_reached: bool = False) -> NativeBaseline:
    second = RAW_STARTED if decision_reached else RAW_COMPLETED
    artifacts = [artifact(), artifact(payload=second, rank=1)]
    imported = reimport_from_raw_artifacts(
        artifacts,
        lambda item: PAYLOADS[item.content_digest],
        binding_artifacts=[binding_artifact(baseline=True), binding_artifact(baseline=False)],
    )
    return generate_native_baseline(
        imported=imported,
        command=["traincapsule", "ingest", "pytorch-flight-recorder"],
        configuration={"mode": "local"},
        elapsed_seconds=10,
        operator_effort_seconds=0,
        unresolved_questions=["Whether to approve the candidate."],
        executed_at=EVALUATED_AT,
        artifact_reader=lambda item: PAYLOADS[item.content_digest],
    )


def complete_report(
    artifacts: list[EvidenceArtifact] | None = None,
):
    artifacts = artifacts or [
        artifact(), artifact(payload=RAW_COMPLETED, rank=1),
        binding_artifact(baseline=True), binding_artifact(baseline=False),
    ]
    return assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={
            "flight_recorder_raw": CompletenessState.PRESENT_VALID,
            "collective_lifecycle": CompletenessState.PRESENT_VALID,
            "rank_process_group_inventory": CompletenessState.PRESENT_VALID,
            "workload_identity": CompletenessState.PRESENT_VALID,
            "environment_identity": CompletenessState.PRESENT_VALID,
        },
        roles={
            name: EvidenceRole.MANDATORY_FOR_ELIGIBILITY
            for name in (
                "flight_recorder_raw", "collective_lifecycle",
                "rank_process_group_inventory", "workload_identity", "environment_identity"
            )
        },
        verified_artifacts=artifacts,
        artifact_refs={name: [item.artifact_id for item in artifacts] for name in (
            "flight_recorder_raw", "collective_lifecycle", "rank_process_group_inventory",
            "workload_identity", "environment_identity"
        )},
        details={"rank_process_group_inventory": "rank/process-group inventory captured"},
    )


def evaluate(inputs: PreflightInputs):
    return evaluate_preflight(inputs, artifact_reader=lambda item: PAYLOADS[item.content_digest])


def make_inputs(**overrides: object) -> PreflightInputs:
    workload = WORKLOAD
    baseline_environment = BASELINE_ENVIRONMENT
    candidate_environment = CANDIDATE_ENVIRONMENT
    artifacts = [
        artifact(), artifact(payload=RAW_COMPLETED, rank=1),
        binding_artifact(baseline=True), binding_artifact(baseline=False),
    ]
    baseline = native_baseline()
    case = IncidentCase(
        case_id="CASE-QUALIFY",
        decision_owner="machine-policy",
        decision_type="candidate approval",
        decision_deadline=DEADLINE,
        incident_summary="controlled collective timeout",
        baseline_environment_id=baseline_environment.environment_id,
        candidate_environment_id=candidate_environment.environment_id,
        workload_id=workload.workload_id,
        evidence_refs=[item.artifact_id for item in artifacts],
        native_findings=baseline.findings,
        pack_candidate="ddp-hang-v1",
        economics=CaseEconomics(),
        privacy_policy="LOCAL_ONLY",
        status="PREFLIGHT",
    )
    values: dict[str, object] = {
        "evaluated_at": EVALUATED_AT,
        "incident_case": case,
        "workload_identity": workload,
        "baseline_environment": baseline_environment,
        "candidate_environment": candidate_environment,
        "verified_artifacts": artifacts,
        "completeness_report": complete_report(),
        "native_baseline": baseline,
        "original_experiment_economics": ExperimentEconomics(
            estimated_cost=100, currency="CAD", basis="measured original run"
        ),
        "proposed_experiment_economics": ExperimentEconomics(
            estimated_cost=10, currency="CAD", basis="bounded proposed experiment"
        ),
    }
    values.update(overrides)
    final_artifacts_value = values["verified_artifacts"]
    final_baseline = values["native_baseline"]
    if isinstance(final_artifacts_value, list) and isinstance(final_baseline, NativeBaseline):
        untyped_artifacts = cast(list[object], final_artifacts_value)
        final_artifacts = [
            item for item in untyped_artifacts if isinstance(item, EvidenceArtifact)
        ]
        if len(final_artifacts) != len(untyped_artifacts):
            raise TypeError("verified_artifacts must contain EvidenceArtifact objects")
        values["incident_case"] = case.model_copy(
            update={
                "evidence_refs": [item.artifact_id for item in final_artifacts],
                "native_findings": final_baseline.findings,
            }
        )
        if "completeness_report" not in overrides:
            values["completeness_report"] = complete_report(final_artifacts)
    return PreflightInputs.model_validate(values)


def test_present_valid_requires_verified_case_bound_artifact_and_role() -> None:
    with pytest.raises((ValidationError, ValueError), match="artifactRef"):
        assess_completeness(
            case_id="CASE-QUALIFY",
            requirements={"trace": CompletenessState.PRESENT_VALID},
            roles={"trace": EvidenceRole.MANDATORY_FOR_ELIGIBILITY},
            verified_artifacts=[artifact()],
        )
    with pytest.raises(ValueError, match="not verified"):
        assess_completeness(
            case_id="CASE-QUALIFY",
            requirements={"trace": CompletenessState.PRESENT_VALID},
            roles={"trace": EvidenceRole.MANDATORY_FOR_ELIGIBILITY},
            verified_artifacts=[artifact()],
            artifact_refs={"trace": ["sha256:" + "e" * 64]},
        )


def test_eligible_decision_is_fully_bound_and_separates_dimensions() -> None:
    decision = evaluate(make_inputs())
    assert decision.outcome is EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION
    assert decision.identity_strength is IdentityStrength.FULLY_VERIFIED
    assert decision.technical_result is TechnicalResult.PASS
    assert decision.operational_decision is OperationalDecision.APPROVE_WITHIN_ENVELOPE
    inputs = make_inputs()
    assert decision.input_digest == digest_json(inputs.model_dump(mode="json", by_alias=True))
    assert decision.workload_id == inputs.workload_identity.workload_id
    assert decision.evidence_refs == sorted(
        item.artifact_id for item in inputs.verified_artifacts
    )
    assert {item.policy.value for item in decision.policy_verifications} == {
        "PACK_FIT",
        "LOCAL_EXECUTION_AUTHORITY",
        "PRIVACY_POLICY",
        "EXPORT_POLICY",
        "SOURCE_VERSION",
        "ECONOMICS",
    }


@pytest.mark.parametrize("policy", ["CUSTOMER_ATTESTED", "UNAVAILABLE"])
def test_weak_identity_can_never_be_laundered_to_approval(policy: str) -> None:
    material = workload_material()
    material["dataIdentity"] = {"policy": policy, "manifestDigest": None}
    weak = build_workload_identity(material)
    inputs = make_inputs()
    case = inputs.incident_case.model_copy(update={"workload_id": weak.workload_id})
    decision = evaluate(
        inputs.model_copy(update={"workload_identity": weak, "incident_case": case})
    )
    assert decision.operational_decision is not OperationalDecision.APPROVE_WITHIN_ENVELOPE
    assert decision.identity_strength is weak.identity_strength


def test_conflicting_identity_needs_more_evidence() -> None:
    material = workload_material()
    material["identityConflict"] = True
    conflicting = build_workload_identity(material)
    inputs = make_inputs()
    case = inputs.incident_case.model_copy(update={"workload_id": conflicting.workload_id})
    decision = evaluate(
        inputs.model_copy(update={"workload_identity": conflicting, "incident_case": case})
    )
    assert decision.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE


def test_cross_case_or_unbound_records_are_rejected() -> None:
    inputs = make_inputs()
    wrong = artifact("OTHER-CASE")
    with pytest.raises(ValidationError, match="cross-case"):
        PreflightInputs.model_validate({**inputs.model_dump(), "verified_artifacts": [wrong]})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        make_inputs(pack_fit={"outcome": "VERIFIED", "verifier": "caller-says-so"})


def test_artifact_uri_must_match_case_and_raw_digest() -> None:
    value = artifact().model_dump()
    value["customer_local_uri"] = f"cas://CASE-QUALIFY/sha256/{'d' * 64}"
    with pytest.raises(ValidationError, match="case-bound URI"):
        EvidenceArtifact.model_validate(value)


def test_zero_human_policy_verifiers_drive_unknown_and_policy_blocked() -> None:
    inputs = make_inputs()
    candidate_material = environment_material()
    candidate_material["scheduler"] = "local"
    candidate_material["materializationRecipeDigest"] = None
    candidate = build_environment_identity(candidate_material)
    case = inputs.incident_case.model_copy(
        update={"candidate_environment_id": candidate.environment_id}
    )
    unknown = evaluate(
        inputs.model_copy(update={"candidate_environment": candidate, "incident_case": case})
    )
    assert unknown.outcome is EligibilityOutcome.UNKNOWN
    blocked_inputs = make_inputs()
    blocked = evaluate(
        blocked_inputs.model_copy(
            update={
                "incident_case": blocked_inputs.incident_case.model_copy(
                    update={"privacy_policy": "EXPORT_ALLOWED"}
                )
            }
        )
    )
    assert blocked.outcome is EligibilityOutcome.POLICY_BLOCKED
    assert "human" not in PreflightInputs.model_fields


def test_caller_cannot_author_native_decision() -> None:
    value = native_baseline().model_dump(mode="json", by_alias=True)
    value["decisionReached"] = "caller says native decided"
    value["decisionEvidenceRefs"] = [DIGEST]
    value["decisionProvenanceDigest"] = digest_json(
        {
            "caseId": "CASE-QUALIFY",
            "decision": value["decisionReached"],
            "evidenceRefs": [DIGEST],
            "policyVersion": "traincapsule-native-sufficiency-v1",
        }
    )
    with pytest.raises(ValidationError, match="generated by the supported policy"):
        NativeBaseline.model_validate(value)


def test_claim_only_and_satisfied_substitute_do_not_block_eligibility() -> None:
    report = assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={
            "trace": CompletenessState.PRESENT_VALID,
            "claim_detail": CompletenessState.MISSING_NOT_CAPTURED,
            "checkpoint": CompletenessState.MISSING_NOT_CAPTURED,
            "manifest": CompletenessState.PRESENT_VALID,
        },
        roles={
            "trace": EvidenceRole.MANDATORY_FOR_ELIGIBILITY,
            "claim_detail": EvidenceRole.MANDATORY_FOR_CLAIM,
            "checkpoint": EvidenceRole.SUBSTITUTABLE,
            "manifest": EvidenceRole.OPTIONAL,
        },
        verified_artifacts=[artifact()],
        artifact_refs={"trace": [DIGEST], "manifest": [DIGEST]},
        claim_names={"claim_detail": ["root-cause"]},
        substitutable_by={"checkpoint": ["manifest"]},
    )
    assert report.technical_result is TechnicalResult.PASS


def test_remaining_controlled_outcomes() -> None:
    missing = assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={"trace": CompletenessState.MISSING_NOT_CAPTURED},
        roles={"trace": EvidenceRole.MANDATORY_FOR_ELIGIBILITY},
        verified_artifacts=[artifact()],
    )
    assert (
        evaluate(make_inputs(completeness_report=missing)).outcome
        is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    )
    sufficient = native_baseline(decision_reached=True)
    sufficient_artifacts = [*sufficient.artifacts, *sufficient.binding_artifacts]
    assert (
        evaluate(
            make_inputs(
                native_baseline=sufficient,
                    verified_artifacts=sufficient_artifacts,
            )
        ).outcome
        is EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT
    )
    assert (
        evaluate(
            make_inputs(
                proposed_experiment_economics=ExperimentEconomics(
                    estimated_cost=101, currency="CAD", basis="bounded proposed experiment"
                )
            )
        ).outcome
        is EligibilityOutcome.TECHNICALLY_POSSIBLE_BUT_UNECONOMIC
    )
    assert (
        evaluate(
            make_inputs(proposed_experiment_economics=ExperimentEconomics(basis="unknown"))
        ).outcome
        is EligibilityOutcome.UNKNOWN
    )
    assert (
        evaluate(
            make_inputs(
                native_baseline=native_baseline().model_copy(update={"tool_version": "9.0"})
            )
        ).outcome
        is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    )


def test_preflight_reopens_and_verifies_raw_case_artifacts() -> None:
    decision = evaluate_preflight(make_inputs(), artifact_reader=lambda _artifact: b"tampered")
    assert decision.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    assert decision.technical_result is TechnicalResult.INVALID_EVIDENCE


def test_exact_native_text_and_self_computed_digest_cannot_forge_sufficiency() -> None:
    value = native_baseline().model_dump(mode="json", by_alias=True)
    decision = (
        "Native evidence is sufficient to block the candidate: "
        "collective lifecycle states disagree."
    )
    value["decisionReached"] = decision
    value["decisionEvidenceRefs"] = [DIGEST]
    value["decisionProvenanceDigest"] = digest_json(
        {
            "caseId": "CASE-QUALIFY",
            "decision": decision,
            "evidenceRefs": [DIGEST],
            "policyVersion": "traincapsule-native-sufficiency-v1",
        }
    )
    forged = NativeBaseline.model_validate(value)
    result = evaluate(make_inputs(native_baseline=forged))
    assert result.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    assert result.technical_result is TechnicalResult.INVALID_EVIDENCE


def test_native_baseline_has_attribution_effort_decision_and_human_rendering() -> None:
    baseline = native_baseline()
    report = render_native_baseline_human(baseline)
    assert baseline.findings[0].attribution is FindingAttribution.NATIVE_TOOL_FOUND
    assert baseline.operator_effort_seconds == 0
    assert "### NATIVE_TOOL_FOUND" in report and "### TRAINCAPSULE_DERIVED" in report
    assert "Configuration:" in report
    assert "## Native findings" in report and "## Unresolved questions" in report


def test_deserialized_identities_reject_strength_and_canonical_id_forgery() -> None:
    workload_payload = WORKLOAD.model_dump(mode="json", by_alias=True)
    workload_payload["identityStrength"] = "CUSTOMER_ATTESTED"
    with pytest.raises(ValidationError, match="identityStrength"):
        type(WORKLOAD).model_validate(workload_payload)

    workload_payload = WORKLOAD.model_dump(mode="json", by_alias=True)
    workload_payload["entrypoint"] = "python attacker.py"
    with pytest.raises(ValidationError, match="workloadId"):
        type(WORKLOAD).model_validate(workload_payload)

    environment_payload = BASELINE_ENVIRONMENT.model_dump(mode="json", by_alias=True)
    environment_payload["scheduler"] = "attacker-controlled"
    with pytest.raises(ValidationError, match="environmentId"):
        type(BASELINE_ENVIRONMENT).model_validate(environment_payload)


def test_caller_optional_completeness_roster_is_recomputed_and_rejected() -> None:
    inputs = make_inputs()
    forged = inputs.completeness_report.model_copy(
        update={
            "requirements": [
                requirement.model_copy(update={"role": EvidenceRole.OPTIONAL})
                if requirement.kind == "rank_process_group_inventory"
                else requirement
                for requirement in inputs.completeness_report.requirements
            ]
        }
    )
    result = evaluate(inputs.model_copy(update={"completeness_report": forged}))
    assert result.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    assert result.technical_result is TechnicalResult.INVALID_EVIDENCE


def test_recomputed_finding_and_import_digest_forgery_are_rejected() -> None:
    inputs = make_inputs()
    baseline_payload = inputs.native_baseline.model_dump(mode="json", by_alias=True)
    findings_value = baseline_payload["findings"]
    assert isinstance(findings_value, list) and findings_value
    finding_payload = cast(dict[str, object], findings_value[0])
    finding_payload["observation"] = "caller-authored observation"
    finding_payload.pop("findingId")
    finding_payload["findingId"] = digest_json(finding_payload)
    baseline_payload["importDigest"] = "sha256:" + "f" * 64
    forged = NativeBaseline.model_validate(baseline_payload)

    result = evaluate(inputs.model_copy(update={"native_baseline": forged}))
    assert result.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    assert result.technical_result is TechnicalResult.INVALID_EVIDENCE


def test_omitted_collective_is_a_native_lifecycle_disagreement() -> None:
    imported = reimport_from_raw_artifacts(
        [artifact(), artifact(payload=RAW_OMITTED, rank=1)],
        lambda item: PAYLOADS[item.content_digest],
        binding_artifacts=[binding_artifact(baseline=True), binding_artifact(baseline=False)],
    )
    baseline = generate_native_baseline(
        imported=imported,
        command=["traincapsule", "ingest", "pytorch-flight-recorder"],
        configuration={"mode": "local"},
        elapsed_seconds=1,
        operator_effort_seconds=0,
        unresolved_questions=[],
        executed_at=EVALUATED_AT,
        artifact_reader=lambda item: PAYLOADS[item.content_digest],
    )
    evidence = [*baseline.artifacts, *baseline.binding_artifacts]
    result = evaluate(
        make_inputs(
            native_baseline=baseline,
            verified_artifacts=evidence,
        )
    )
    assert result.outcome is EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT


def test_native_sufficiency_precedes_unknown_experiment_economics() -> None:
    sufficient = native_baseline(decision_reached=True)
    evidence = [*sufficient.artifacts, *sufficient.binding_artifacts]
    result = evaluate(
        make_inputs(
            native_baseline=sufficient,
            verified_artifacts=evidence,
            proposed_experiment_economics=ExperimentEconomics(basis="unknown"),
        )
    )
    assert result.outcome is EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT


def test_native_machine_and_human_reports_redact_user_secrets() -> None:
    imported = reimport_from_raw_artifacts(
        [artifact(), artifact(payload=RAW_COMPLETED, rank=1)],
        lambda item: PAYLOADS[item.content_digest],
        binding_artifacts=[binding_artifact(baseline=True), binding_artifact(baseline=False)],
    )
    baseline = generate_native_baseline(
        imported=imported,
        command=["collector", "--password", "very-secret", "token=also-secret"],
        configuration={
            "nested": {"api_key": "config-secret"},
            "url": "https://user:password@example.test/path",
        },
        elapsed_seconds=1,
        operator_effort_seconds=0,
        unresolved_questions=["Can bearer very-secret be reused? token=question-secret"],
        executed_at=EVALUATED_AT,
        artifact_reader=lambda item: PAYLOADS[item.content_digest],
    )
    machine = baseline.model_dump_json()
    human = render_native_baseline_human(baseline)
    for secret in (
        "very-secret",
        "also-secret",
        "config-secret",
        "password@example",
        "question-secret",
    ):
        assert secret not in machine
        assert secret not in human


def test_pytorch_version_lookalike_is_not_supported() -> None:
    raw_rank_0 = RAW.replace(b"2.5.1", b"2.5evil")
    raw_rank_1 = RAW_COMPLETED.replace(b"2.5.1", b"2.5evil")
    evidence = [
        artifact(payload=raw_rank_0, rank=0),
        artifact(payload=raw_rank_1, rank=1),
    ]
    bindings = [binding_artifact(baseline=True), binding_artifact(baseline=False)]
    payloads = {
        sha256_digest(raw_rank_0): raw_rank_0,
        sha256_digest(raw_rank_1): raw_rank_1,
        sha256_digest(BASELINE_RECIPE): BASELINE_RECIPE,
        sha256_digest(CANDIDATE_RECIPE): CANDIDATE_RECIPE,
    }
    def reader(item: EvidenceArtifact) -> bytes:
        return payloads[item.content_digest]
    imported = reimport_from_raw_artifacts(
        evidence, reader, binding_artifacts=bindings
    )
    baseline = generate_native_baseline(
        imported=imported,
        command=["collector"],
        configuration={},
        elapsed_seconds=1,
        operator_effort_seconds=0,
        unresolved_questions=["No supported native version."],
        executed_at=EVALUATED_AT,
        artifact_reader=reader,
    )
    all_evidence = [*evidence, *bindings]
    decision = evaluate_preflight(
        make_inputs(
            native_baseline=baseline,
            verified_artifacts=all_evidence,
            completeness_report=complete_report(all_evidence),
        ),
        artifact_reader=reader,
    )
    assert decision.outcome is EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE


def test_human_native_report_neutralizes_markdown_control_injection() -> None:
    payload = native_baseline().model_dump(mode="json", by_alias=True)
    payload["unresolvedQuestions"] = [
        "question\n\n## Decision reached\n\nAPPROVE_WITHIN_ENVELOPE"
    ]
    baseline = NativeBaseline.model_validate(payload)
    report = render_native_baseline_human(baseline)
    assert report.count("\n## Decision reached") == 1
    assert "\nAPPROVE_WITHIN_ENVELOPE" not in report
    assert "question  ## Decision reached  APPROVE_WITHIN_ENVELOPE" in report


def qualification_store(tmp_path: Path, inputs: PreflightInputs) -> LocalEvidenceStore:
    store = LocalEvidenceStore(tmp_path / "store")
    for artifact_record in inputs.verified_artifacts:
        stored = store.put_bytes(
            case_id=artifact_record.case_id,
            payload=PAYLOADS[artifact_record.content_digest],
            kind=artifact_record.kind,
            source_adapter=artifact_record.source_adapter,
            source_version=artifact_record.source_version,
            captured_at=artifact_record.captured_at,
            privacy_class=artifact_record.privacy_class,
            provenance=artifact_record.provenance,
            workload_id=artifact_record.workload_id,
            baseline_environment_id=artifact_record.baseline_environment_id,
            candidate_environment_id=artifact_record.candidate_environment_id,
        )
        assert stored == artifact_record
    return store


def qualification_specification(
    tmp_path: Path, inputs: PreflightInputs, *, candidate_text: str = "fixed"
) -> ExperimentSpecification:
    executable = str(Path(sys.executable).resolve())
    return ExperimentSpecification(
        case_id=inputs.incident_case.case_id,
        workload_id=inputs.workload_identity.workload_id,
        baseline_environment_id=inputs.baseline_environment.environment_id,
        candidate_environment_id=inputs.candidate_environment.environment_id,
        hypothesis="The candidate removes the observed collective lifecycle failure.",
        observed_boundary="Process exit and customer-local stdout.",
        manipulated_variables={"environment": "candidate identity"},
        controlled_variables={"workload": "fully verified workload identity"},
        expected_observations=["baseline reproduces", "candidate reports fixed"],
        legal_transformations=["candidate environment substitution"],
        forbidden_transformations=["workload or oracle substitution"],
        baseline_command=[executable, "-c", "print('incident')"],
        candidate_command=[executable, "-c", f"print('{candidate_text}')"],
        working_directory=str(tmp_path.resolve()),
        timeout_seconds=5,
        max_output_bytes=4096,
        stop_conditions=["timeout", "combined output limit"],
        baseline_expectation=CommandExpectation(
            expected_exit_codes=[0], required_stdout_tokens=["incident"]
        ),
        candidate_expectation=CommandExpectation(
            expected_exit_codes=[0], required_stdout_tokens=["fixed"]
        ),
        result_semantics="PASS requires baseline reproduction and candidate oracle success.",
    )


def test_customer_local_runner_qualifies_a_bound_candidate(tmp_path: Path) -> None:
    inputs = make_inputs()
    decision = execute_qualification(
        inputs,
        qualification_specification(tmp_path, inputs),
        store=qualification_store(tmp_path, inputs),
        now=lambda: EVALUATED_AT,
    )

    assert decision.result is QualificationResult.PASS
    assert decision.baseline_run is not None and decision.baseline_run.expectation_met
    assert decision.candidate_run is not None and decision.candidate_run.expectation_met
    assert len(decision.evidence_refs) >= len(inputs.verified_artifacts) + 4


def test_candidate_oracle_failure_is_a_qualification_fail(tmp_path: Path) -> None:
    inputs = make_inputs()
    decision = execute_qualification(
        inputs,
        qualification_specification(tmp_path, inputs, candidate_text="still broken"),
        store=qualification_store(tmp_path, inputs),
        now=lambda: EVALUATED_AT,
    )

    assert decision.result is QualificationResult.FAIL
    assert decision.baseline_run is not None and decision.baseline_run.expectation_met
    assert decision.candidate_run is not None and not decision.candidate_run.expectation_met


def test_preflight_blocks_local_command_execution(tmp_path: Path) -> None:
    inputs = make_inputs()
    inputs = inputs.model_copy(
        update={
            "incident_case": inputs.incident_case.model_copy(
                update={"privacy_policy": "EXPORT_ALLOWED"}
            )
        }
    )
    marker = tmp_path / "must-not-exist"
    specification = qualification_specification(tmp_path, inputs)
    specification = specification.model_copy(
        update={
            "baseline_command": [
                str(Path(sys.executable).resolve()),
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).touch()",
            ]
        }
    )
    decision = execute_qualification(
        inputs,
        specification,
        store=qualification_store(tmp_path, inputs),
        now=lambda: EVALUATED_AT,
    )

    assert decision.result is QualificationResult.INAPPLICABLE
    assert decision.baseline_run is None
    assert not marker.exists()


def test_output_budget_stops_before_candidate_execution(tmp_path: Path) -> None:
    inputs = make_inputs()
    marker = tmp_path / "candidate-must-not-run"
    specification = qualification_specification(tmp_path, inputs).model_copy(
        update={
            "baseline_command": [
                str(Path(sys.executable).resolve()),
                "-c",
                "print('x' * 5000)",
            ],
            "candidate_command": [
                str(Path(sys.executable).resolve()),
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).touch()",
            ],
            "max_output_bytes": 1024,
        }
    )
    decision = execute_qualification(
        inputs,
        specification,
        store=qualification_store(tmp_path, inputs),
        now=lambda: EVALUATED_AT,
    )

    assert decision.result is QualificationResult.UNKNOWN
    assert decision.baseline_run is not None
    assert decision.baseline_run.output_limit_exceeded
    assert decision.candidate_run is None
    assert not marker.exists()
