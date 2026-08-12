from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from traincapsule_core.models import (
    CompletenessState,
    EligibilityOutcome,
    NativeConfidence,
    NativeFinding,
    OperationalDecision,
    TechnicalResult,
)
from traincapsule_qualify import (
    CostHypothesis,
    NativeBaseline,
    PreflightInputs,
    assess_completeness,
    evaluate_preflight,
)

DIGEST = "sha256:" + "d" * 64
EVALUATED_AT = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
DEADLINE = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def native_finding() -> NativeFinding:
    return NativeFinding(
        finding_id=DIGEST,
        native_system="PyTorch Flight Recorder",
        native_version="2.5.1",
        observation="Rank 1 reported an unfinished all_reduce.",
        evidence_refs=[DIGEST],
        confidence_class=NativeConfidence.DIRECT_OBSERVATION,
        limitations=["This observation does not establish root cause."],
        customer_decision_contribution="Establishes the native baseline.",
    )


def native_baseline() -> NativeBaseline:
    return NativeBaseline(
        case_id="CASE-QUALIFY",
        tool_name="PyTorch Flight Recorder",
        tool_version="2.5.1",
        command=["torchfr", "analyze", "local-trace"],
        configuration={"mode": "local"},
        findings=[native_finding()],
        evidence_refs=[DIGEST],
        limitations=["Native evidence alone may not discriminate candidate safety."],
        unresolved_customer_decision="Whether to approve the candidate environment.",
        executed_at=EVALUATED_AT,
        human_reviewed=True,
        reviewer="customer-incident-owner",
    )


def complete_report():
    return assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={
            "flight_recorder": CompletenessState.PRESENT_VALID,
            "checkpoint": CompletenessState.NOT_APPLICABLE,
        },
        artifact_refs={"flight_recorder": [DIGEST]},
    )


def make_inputs(**overrides: object) -> PreflightInputs:
    values: dict[str, object] = {
        "case_id": "CASE-QUALIFY",
        "decision_type": "candidate approval",
        "decision_deadline": DEADLINE,
        "evaluated_at": EVALUATED_AT,
        "baseline_access": True,
        "candidate_access": True,
        "evidence_identity_bound": True,
        "pack_fit": True,
        "local_execution_available": True,
        "cost_hypothesis": CostHypothesis.VIABLE,
        "privacy_policy_allows_processing": True,
        "export_policy_allows_required_flow": True,
        "complete_native_baseline": True,
        "native_workflow_resolves_decision": False,
        "human_expertise_available": True,
        "source_version_supported": True,
        "completeness_report": complete_report(),
        "native_baseline": native_baseline(),
    }
    values.update(overrides)
    return PreflightInputs.model_validate(values)


def test_all_completeness_states_are_exact_and_incomplete_never_passes() -> None:
    assert {state.value for state in CompletenessState} == {
        "PRESENT_VALID",
        "PRESENT_PARTIAL",
        "PRESENT_CONFLICTING",
        "PRESENT_CORRUPTED",
        "MISSING_NOT_CAPTURED",
        "MISSING_POLICY_RESTRICTED",
        "MISSING_TECHNICALLY_INACCESSIBLE",
        "MISSING_VERSION_UNSUPPORTED",
        "IDENTITY_UNBOUND",
        "NOT_APPLICABLE",
    }
    corrupted = assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={"trace": CompletenessState.PRESENT_CORRUPTED},
    )
    assert corrupted.technical_result is TechnicalResult.INVALID_EVIDENCE


def test_eligible_journey_keeps_technical_and_operational_dimensions_separate() -> None:
    decision = evaluate_preflight(make_inputs())
    assert decision.outcome is EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION
    assert decision.technical_result is TechnicalResult.PASS
    assert decision.operational_decision is OperationalDecision.APPROVE_WITHIN_ENVELOPE
    assert TechnicalResult.__module__ == "traincapsule_core.models"
    assert OperationalDecision.__module__ == "traincapsule_core.models"


@pytest.mark.parametrize(
    ("changes", "outcome", "technical", "operational"),
    [
        (
            {"baseline_access": False},
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            TechnicalResult.UNKNOWN,
            OperationalDecision.REQUIRE_MORE_EVIDENCE,
        ),
        (
            {"native_workflow_resolves_decision": True},
            EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT,
            TechnicalResult.PASS,
            OperationalDecision.NATIVE_WORKFLOW_SUFFICIENT,
        ),
        (
            {"privacy_policy_allows_processing": False},
            EligibilityOutcome.POLICY_BLOCKED,
            TechnicalResult.POLICY_BLOCKED,
            OperationalDecision.BLOCK_CHANGE,
        ),
        (
            {"source_version_supported": False},
            EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE,
            TechnicalResult.UNKNOWN,
            OperationalDecision.BLOCK_CHANGE,
        ),
        (
            {"cost_hypothesis": CostHypothesis.UNKNOWN},
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.UNKNOWN,
            OperationalDecision.NO_DECISION,
        ),
        (
            {"cost_hypothesis": CostHypothesis.UNECONOMIC},
            EligibilityOutcome.TECHNICALLY_POSSIBLE_BUT_UNECONOMIC,
            TechnicalResult.PASS,
            OperationalDecision.TECHNICALLY_VALID_BUT_NOT_ECONOMIC,
        ),
        (
            {"human_expertise_available": False},
            EligibilityOutcome.ELIGIBLE_WITH_HUMAN_REVIEW,
            TechnicalResult.PASS,
            OperationalDecision.NO_DECISION,
        ),
        (
            {"evaluated_at": datetime(2026, 8, 13, tzinfo=UTC)},
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.EXPIRED,
            OperationalDecision.NO_DECISION,
        ),
    ],
)
def test_controlled_preflight_outcomes(
    changes: dict[str, object],
    outcome: EligibilityOutcome,
    technical: TechnicalResult,
    operational: OperationalDecision,
) -> None:
    decision = evaluate_preflight(make_inputs(**changes))
    assert decision.outcome is outcome
    assert decision.technical_result is technical
    assert decision.operational_decision is operational


def test_complete_native_baseline_claim_requires_the_record() -> None:
    with pytest.raises(ValidationError, match="requires nativeBaseline"):
        make_inputs(native_baseline=None)


def test_native_sufficiency_cannot_be_claimed_from_incomplete_baseline() -> None:
    with pytest.raises(ValidationError, match="without a complete baseline"):
        make_inputs(
            complete_native_baseline=False,
            native_workflow_resolves_decision=True,
            native_baseline=None,
        )


def test_corrupted_evidence_keeps_invalid_technical_truth() -> None:
    report = assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={"trace": CompletenessState.PRESENT_CORRUPTED},
    )
    decision = evaluate_preflight(make_inputs(completeness_report=report))
    assert decision.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    assert decision.technical_result is TechnicalResult.INVALID_EVIDENCE
    assert decision.operational_decision is OperationalDecision.REQUIRE_MORE_EVIDENCE
