from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from traincapsule_core import (
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
    NativeConfidence,
    NativeFinding,
    OperationalDecision,
    PrivacyClass,
    TechnicalResult,
)
from traincapsule_qualify import (
    NativeBaseline,
    PreflightInputs,
    assess_completeness,
    evaluate_preflight,
    render_native_baseline_human,
)

from .test_identity import environment_material, workload_material


def test_zero_human_outcome_vocabulary_has_no_intervention_state() -> None:
    assert "ELIGIBLE_WITH_HUMAN_REVIEW" not in EligibilityOutcome.__members__


RAW = (
    b'{"entries":[{"collective_seq_id":42,"profiling_name":"nccl:all_reduce",'
    b'"state":"completed"}],"pg_id":"0","pytorch_version":"2.5.1","rank":0,'
    b'"version":"2.5","world_size":1}'
)
RAW_STARTED = (
    b'{"entries":[{"collective_seq_id":42,"profiling_name":"nccl:all_reduce",'
    b'"state":"started"}],"pg_id":"0","pytorch_version":"2.5.1","rank":1,'
    b'"version":"2.5","world_size":2}'
)
DIGEST = sha256_digest(RAW)
EVALUATED_AT = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
DEADLINE = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def artifact(
    case_id: str = "CASE-QUALIFY", *, payload: bytes = RAW, rank: int = 0
) -> EvidenceArtifact:
    digest = sha256_digest(payload)
    return EvidenceArtifact(
        artifact_id=digest,
        case_id=case_id,
        kind="PYTORCH_FLIGHT_RECORDER_RAW",
        source_adapter="pytorch-flight-recorder",
        source_version="1.0",
        captured_at=EVALUATED_AT,
        content_digest=digest,
        size_bytes=len(payload),
        privacy_class=PrivacyClass.CONFIDENTIAL,
        customer_local_uri=f"cas://{case_id}/sha256/{digest.removeprefix('sha256:')}",
        export_policy="LOCAL_ONLY",
        provenance={"sourceRelativePath": f"rank-{rank}.json"},
        integrity_status=EvidenceIntegrity.VALID,
    )


def native_finding(evidence_refs: list[str] | None = None) -> NativeFinding:
    refs = evidence_refs or [DIGEST]
    return NativeFinding(
        finding_id=DIGEST,
        attribution=FindingAttribution.NATIVE_TOOL_FOUND,
        native_system="PyTorch Flight Recorder",
        native_version="2.5.1",
        observation="Rank 1 directly reported an unfinished all_reduce.",
        evidence_refs=refs,
        confidence_class=NativeConfidence.DIRECT_OBSERVATION,
        limitations=["This observation does not establish root cause."],
        customer_decision_contribution="Preserves the native observation.",
    )


def native_baseline(*, decision_reached: bool = False) -> NativeBaseline:
    decision = (
        "Native evidence is sufficient to block the candidate: "
        "collective lifecycle states disagree."
        if decision_reached
        else None
    )
    artifacts = [artifact()]
    if decision:
        artifacts.append(artifact(payload=RAW_STARTED, rank=1))
    artifact_ids = [item.artifact_id for item in artifacts]
    decision_refs = sorted(artifact_ids) if decision else []
    decision_digest = (
        digest_json(
            {
                "caseId": "CASE-QUALIFY",
                "decision": decision,
                "evidenceRefs": decision_refs,
                "policyVersion": "traincapsule-native-sufficiency-v1",
            }
        )
        if decision
        else None
    )
    return NativeBaseline(
        case_id="CASE-QUALIFY",
        tool_name="PyTorch Flight Recorder",
        tool_version="2.5.1",
        command=["traincapsule", "ingest", "pytorch-flight-recorder"],
        configuration={"mode": "local"},
        artifacts=artifacts,
        findings=[native_finding(artifact_ids)],
        limitations=["Native evidence does not establish candidate safety."],
        elapsed_seconds=10,
        operator_effort_seconds=0,
        decision_reached=decision,
        decision_evidence_refs=decision_refs,
        decision_provenance_digest=decision_digest,
        unresolved_questions=[] if decision else ["Whether to approve the candidate."],
        executed_at=EVALUATED_AT,
    )


def complete_report():
    return assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={
            "flight_recorder": CompletenessState.PRESENT_VALID,
            "checkpoint": CompletenessState.NOT_APPLICABLE,
        },
        roles={
            "flight_recorder": EvidenceRole.MANDATORY_FOR_ELIGIBILITY,
            "checkpoint": EvidenceRole.OPTIONAL,
        },
        verified_artifacts=[artifact()],
        artifact_refs={"flight_recorder": [DIGEST]},
    )


def evaluate(inputs: PreflightInputs):
    payloads = {DIGEST: RAW, sha256_digest(RAW_STARTED): RAW_STARTED}
    return evaluate_preflight(inputs, artifact_reader=lambda item: payloads[item.content_digest])


def make_inputs(**overrides: object) -> PreflightInputs:
    workload = build_workload_identity(workload_material())
    baseline_environment = build_environment_identity(environment_material())
    candidate_material = environment_material()
    candidate_material["scheduler"] = "local"
    candidate_environment = build_environment_identity(candidate_material)
    case = IncidentCase(
        case_id="CASE-QUALIFY",
        decision_owner="machine-policy",
        decision_type="candidate approval",
        decision_deadline=DEADLINE,
        incident_summary="controlled collective timeout",
        baseline_environment_id=baseline_environment.environment_id,
        candidate_environment_id=candidate_environment.environment_id,
        workload_id=workload.workload_id,
        evidence_refs=[DIGEST],
        native_findings=[native_finding()],
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
        "verified_artifacts": [artifact()],
        "completeness_report": complete_report(),
        "native_baseline": native_baseline(),
        "original_experiment_economics": ExperimentEconomics(
            estimated_cost=100, currency="CAD", basis="measured original run"
        ),
        "proposed_experiment_economics": ExperimentEconomics(
            estimated_cost=10, currency="CAD", basis="bounded proposed experiment"
        ),
    }
    values.update(overrides)
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
    assert decision.evidence_refs == [DIGEST]
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
    assert (
        evaluate(
            make_inputs(
                native_baseline=sufficient,
                verified_artifacts=sufficient.artifacts,
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
        is EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE
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
