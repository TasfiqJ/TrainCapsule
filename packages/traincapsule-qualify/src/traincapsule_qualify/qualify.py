"""Deterministic evidence-completeness and eligibility evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from traincapsule_core.models import (
    CompletenessState,
    EligibilityDecision,
    EligibilityOutcome,
    EvidenceCompletenessReport,
    EvidenceRequirement,
    OperationalDecision,
    TechnicalResult,
)

from .models import CostHypothesis, PreflightInputs


def assess_completeness(
    *,
    case_id: str,
    requirements: Mapping[str, CompletenessState],
    artifact_refs: Mapping[str, Iterable[str]] | None = None,
    details: Mapping[str, str] | None = None,
) -> EvidenceCompletenessReport:
    """Create a stable report without converting missing or weak evidence to valid."""
    refs = artifact_refs or {}
    explanations = details or {}
    ordered = [
        EvidenceRequirement(
            kind=kind,
            state=state,
            artifact_refs=sorted(refs.get(kind, [])),
            detail=explanations.get(kind, state.value),
        )
        for kind, state in sorted(requirements.items())
    ]
    invalid_states = {
        CompletenessState.PRESENT_CORRUPTED,
        CompletenessState.PRESENT_CONFLICTING,
    }
    if any(item.state in invalid_states for item in ordered):
        result = TechnicalResult.INVALID_EVIDENCE
    elif all(
        item.state in {CompletenessState.PRESENT_VALID, CompletenessState.NOT_APPLICABLE}
        for item in ordered
    ):
        result = TechnicalResult.PASS
    else:
        result = TechnicalResult.UNKNOWN
    return EvidenceCompletenessReport(
        case_id=case_id,
        requirements=ordered,
        technical_result=result,
    )


def evaluate_preflight(inputs: PreflightInputs) -> EligibilityDecision:
    """Evaluate product eligibility with explicit unknowns and stable precedence."""
    reasons: list[str] = []
    unknowns: list[str] = []

    policy_values = {
        "privacy processing permission": inputs.privacy_policy_allows_processing,
        "required evidence export permission": inputs.export_policy_allows_required_flow,
    }
    denied = [name for name, value in policy_values.items() if value is False]
    if denied:
        return _decision(
            inputs,
            EligibilityOutcome.POLICY_BLOCKED,
            TechnicalResult.POLICY_BLOCKED,
            [f"Policy denies {name}." for name in denied],
            [],
        )

    if inputs.evaluated_at > inputs.decision_deadline:
        return _decision(
            inputs,
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.EXPIRED,
            ["The named customer decision deadline has passed."],
            [],
        )

    if inputs.source_version_supported is False:
        return _decision(
            inputs,
            EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE,
            TechnicalResult.UNKNOWN,
            ["The supplied evidence version is outside the supported envelope."],
            [],
        )

    if inputs.pack_fit is False or inputs.local_execution_available is False:
        if inputs.pack_fit is False:
            reasons.append("No controlled qualification pack fits the case.")
        if inputs.local_execution_available is False:
            reasons.append("Required customer-local execution is unavailable.")
        return _decision(
            inputs,
            EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE,
            TechnicalResult.UNKNOWN,
            reasons,
            [],
        )

    if (
        inputs.complete_native_baseline is True
        and inputs.native_workflow_resolves_decision is True
    ):
        return _decision(
            inputs,
            EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT,
            TechnicalResult.PASS,
            ["The complete native workflow already resolves the named decision."],
            [],
        )

    access_values = {
        "baseline access": inputs.baseline_access,
        "candidate access": inputs.candidate_access,
        "evidence identity binding": inputs.evidence_identity_bound,
    }
    missing = [name for name, value in access_values.items() if value is False]
    if inputs.completeness_report.technical_result is not TechnicalResult.PASS:
        missing.append("complete valid evidence")
    if missing:
        incomplete_result = inputs.completeness_report.technical_result
        technical_result = (
            incomplete_result
            if incomplete_result
            in {TechnicalResult.INVALID_EVIDENCE, TechnicalResult.INVALID_ORACLE}
            else TechnicalResult.UNKNOWN
        )
        return _decision(
            inputs,
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            technical_result,
            [f"Qualification requires {name}." for name in missing],
            [],
        )

    if inputs.cost_hypothesis is CostHypothesis.UNECONOMIC:
        return _decision(
            inputs,
            EligibilityOutcome.TECHNICALLY_POSSIBLE_BUT_UNECONOMIC,
            TechnicalResult.PASS,
            ["The supplied cost hypothesis says qualification is uneconomic."],
            [],
        )

    unknown_values = {
        "baseline access": inputs.baseline_access,
        "candidate access": inputs.candidate_access,
        "evidence identity binding": inputs.evidence_identity_bound,
        "qualification pack fit": inputs.pack_fit,
        "customer-local execution": inputs.local_execution_available,
        "privacy processing permission": inputs.privacy_policy_allows_processing,
        "required evidence export permission": inputs.export_policy_allows_required_flow,
        "native baseline completeness": inputs.complete_native_baseline,
        "native workflow sufficiency": inputs.native_workflow_resolves_decision,
        "source version support": inputs.source_version_supported,
    }
    unknowns.extend(name for name, value in unknown_values.items() if value is None)
    if inputs.cost_hypothesis is CostHypothesis.UNKNOWN:
        unknowns.append("qualification cost hypothesis")
    if unknowns:
        return _decision(
            inputs,
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.UNKNOWN,
            ["One or more required preflight inputs are unknown."],
            sorted(unknowns),
        )

    if inputs.human_expertise_available is not True:
        if inputs.human_expertise_available is None:
            unknowns.append("human expertise availability")
        return _decision(
            inputs,
            EligibilityOutcome.ELIGIBLE_WITH_HUMAN_REVIEW,
            TechnicalResult.PASS,
            ["Technical preflight passed, but qualified human review must be arranged."],
            unknowns,
        )

    return _decision(
        inputs,
        EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION,
        TechnicalResult.PASS,
        ["All controlled qualification prerequisites are explicitly satisfied."],
        [],
    )


def _decision(
    inputs: PreflightInputs,
    outcome: EligibilityOutcome,
    technical_result: TechnicalResult,
    reasons: list[str],
    unknowns: list[str],
) -> EligibilityDecision:
    decisions = {
        EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION: OperationalDecision.APPROVE_WITHIN_ENVELOPE,
        EligibilityOutcome.ELIGIBLE_WITH_HUMAN_REVIEW: OperationalDecision.NO_DECISION,
        EligibilityOutcome.NEEDS_MORE_EVIDENCE: OperationalDecision.REQUIRE_MORE_EVIDENCE,
        EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT: (
            OperationalDecision.NATIVE_WORKFLOW_SUFFICIENT
        ),
        EligibilityOutcome.TECHNICALLY_POSSIBLE_BUT_UNECONOMIC: (
            OperationalDecision.TECHNICALLY_VALID_BUT_NOT_ECONOMIC
        ),
        EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE: OperationalDecision.BLOCK_CHANGE,
        EligibilityOutcome.POLICY_BLOCKED: OperationalDecision.BLOCK_CHANGE,
        EligibilityOutcome.UNKNOWN: OperationalDecision.NO_DECISION,
    }
    return EligibilityDecision(
        case_id=inputs.case_id,
        outcome=outcome,
        technical_result=technical_result,
        operational_decision=decisions[outcome],
        reasons=reasons,
        unknowns=unknowns,
        generated_at=inputs.evaluated_at,
    )
