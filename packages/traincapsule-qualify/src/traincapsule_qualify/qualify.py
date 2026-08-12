"""Deterministic completeness, native-baseline, and preflight evaluation."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from traincapsule_core.base import digest_json, sha256_digest
from traincapsule_core.models import (
    CompletenessState,
    EligibilityDecision,
    EligibilityOutcome,
    EvidenceArtifact,
    EvidenceCompletenessReport,
    EvidenceRequirement,
    EvidenceRole,
    FindingAttribution,
    IdentityStrength,
    MachineVerification,
    OperationalDecision,
    PolicyName,
    TechnicalResult,
    VerificationOutcome,
)
from traincapsule_ingest_pytorch import (
    FlightRecorderImport,
    FlightRecorderImportError,
    lifecycle_disagreement_from_raw,
    verify_import_against_raw,
)

from .models import NATIVE_SUFFICIENT_DECISION, NativeBaseline, PreflightInputs

_SUPPORTED_PACKS = frozenset({"ddp-hang-v1"})
_SUPPORTED_NATIVE_TOOL = "PyTorch Flight Recorder"
_SUPPORTED_PYTORCH_PREFIXES = ("2.5",)


def assess_completeness(
    *,
    case_id: str,
    requirements: Mapping[str, CompletenessState],
    roles: Mapping[str, EvidenceRole],
    verified_artifacts: Iterable[EvidenceArtifact],
    artifact_refs: Mapping[str, Iterable[str]] | None = None,
    details: Mapping[str, str] | None = None,
    claim_names: Mapping[str, Iterable[str]] | None = None,
    substitutable_by: Mapping[str, Iterable[str]] | None = None,
) -> EvidenceCompletenessReport:
    """Build completeness only from case-bound, digest-verified artifact metadata."""
    refs = artifact_refs or {}
    explanations = details or {}
    claims = claim_names or {}
    substitutes = substitutable_by or {}
    verified = {
        artifact.artifact_id
        for artifact in verified_artifacts
        if artifact.case_id == case_id and artifact.integrity_status.value == "VALID"
    }
    if set(requirements) != set(roles):
        raise ValueError("every evidence requirement needs an explicit role")
    ordered: list[EvidenceRequirement] = []
    for kind, state in sorted(requirements.items()):
        cited = sorted(refs.get(kind, []))
        if not set(cited) <= verified:
            raise ValueError(f"{kind} references evidence not verified for this case")
        ordered.append(
            EvidenceRequirement(
                kind=kind,
                role=roles[kind],
                claim_names=sorted(claims.get(kind, [])),
                substitutable_by=sorted(substitutes.get(kind, [])),
                state=state,
                artifact_refs=cited,
                detail=explanations.get(kind, state.value),
            )
        )
    invalid = {CompletenessState.PRESENT_CORRUPTED, CompletenessState.PRESENT_CONFLICTING}
    by_kind = {item.kind: item for item in ordered}
    blocking = [item for item in ordered if item.role is EvidenceRole.MANDATORY_FOR_ELIGIBILITY]
    substitutes = [item for item in ordered if item.role is EvidenceRole.SUBSTITUTABLE]
    unresolved_substitutes = [
        item
        for item in substitutes
        if item.state is not CompletenessState.PRESENT_VALID
        and not any(
            by_kind.get(name) is not None and by_kind[name].state is CompletenessState.PRESENT_VALID
            for name in item.substitutable_by
        )
    ]
    blocking.extend(unresolved_substitutes)
    if any(item.state in invalid for item in blocking):
        result = TechnicalResult.INVALID_EVIDENCE
    elif all(
        item.state in {CompletenessState.PRESENT_VALID, CompletenessState.NOT_APPLICABLE}
        for item in blocking
    ):
        result = TechnicalResult.PASS
    else:
        result = TechnicalResult.UNKNOWN
    return EvidenceCompletenessReport(
        case_id=case_id, requirements=ordered, technical_result=result
    )


def generate_native_baseline(
    *,
    imported: FlightRecorderImport,
    command: list[str],
    configuration: Mapping[str, object],
    elapsed_seconds: int,
    operator_effort_seconds: int,
    unresolved_questions: list[str],
    executed_at: datetime,
    artifact_reader: Callable[[EvidenceArtifact], bytes],
) -> NativeBaseline:
    """Generate a bound native record from importer output rather than echoing caller JSON."""
    limitations = sorted(
        {limitation for finding in imported.native_findings for limitation in finding.limitations}
    )
    lifecycle_disagreement = verify_import_against_raw(imported, artifact_reader)
    decision = NATIVE_SUFFICIENT_DECISION if lifecycle_disagreement else None
    decision_refs = (
        sorted(artifact.artifact_id for artifact in imported.artifacts)
        if lifecycle_disagreement
        else []
    )
    decision_digest = (
        digest_json(
            {
                "caseId": imported.case_id,
                "decision": decision,
                "evidenceRefs": decision_refs,
                "policyVersion": "traincapsule-native-sufficiency-v1",
            }
        )
        if decision is not None
        else None
    )
    return NativeBaseline(
        case_id=imported.case_id,
        tool_name="PyTorch Flight Recorder",
        tool_version=imported.pytorch_version,
        command=command,
        configuration=dict(configuration),
        artifacts=imported.artifacts,
        findings=imported.native_findings,
        limitations=limitations,
        elapsed_seconds=elapsed_seconds,
        operator_effort_seconds=operator_effort_seconds,
        decision_reached=decision,
        decision_evidence_refs=decision_refs,
        decision_provenance_digest=decision_digest,
        unresolved_questions=[] if decision else unresolved_questions,
        executed_at=executed_at,
    )


def render_native_baseline_human(baseline: NativeBaseline) -> str:
    decision = baseline.decision_reached or "No native decision reached."
    finding_sections: list[str] = []
    for attribution in FindingAttribution:
        attributed = [item for item in baseline.findings if item.attribution is attribution]
        body = "\n".join(f"- {item.observation}" for item in attributed) or "- None"
        finding_sections.append(f"### {attribution.value}\n\n{body}")
    findings = "\n\n".join(finding_sections)
    limitations = "\n".join(f"- {item}" for item in baseline.limitations)
    questions = "\n".join(f"- {item}" for item in baseline.unresolved_questions) or "- None"
    return (
        f"# Native baseline — {baseline.case_id}\n\n"
        f"Tool: {baseline.tool_name} {baseline.tool_version}\n\n"
        f"Command: `{' '.join(baseline.command)}`\n\n"
        f"Configuration: `{baseline.configuration}`\n\n"
        f"Elapsed: {baseline.elapsed_seconds}s; operator effort: "
        f"{baseline.operator_effort_seconds}s\n\n"
        f"## Native findings\n\n{findings}\n\n"
        f"## Limitations\n\n{limitations}\n\n"
        f"## Decision reached\n\n{decision}\n\n"
        f"## Unresolved questions\n\n{questions}\n"
    )


def _identity_strength(inputs: PreflightInputs) -> IdentityStrength:
    strengths = {
        inputs.workload_identity.identity_strength,
        inputs.baseline_environment.identity_strength,
        inputs.candidate_environment.identity_strength,
    }
    precedence = (
        IdentityStrength.CONFLICTING,
        IdentityStrength.UNVERIFIED,
        IdentityStrength.CUSTOMER_ATTESTED,
        IdentityStrength.PARTIALLY_VERIFIED,
        IdentityStrength.FULLY_VERIFIED,
    )
    return next(item for item in precedence if item in strengths)


def _verification(
    policy: PolicyName,
    outcome: VerificationOutcome,
    subject: object,
    reason: str,
) -> MachineVerification:
    return MachineVerification(
        policy=policy,
        outcome=outcome,
        subject_digest=digest_json(subject),
        reason=reason,
    )


def _policy_verifications(inputs: PreflightInputs) -> list[MachineVerification]:
    case = inputs.incident_case
    pack_supported = case.pack_candidate in _SUPPORTED_PACKS
    access_known = all(
        environment.materialization_recipe_digest is not None
        for environment in (inputs.baseline_environment, inputs.candidate_environment)
    )
    privacy_supported = case.privacy_policy == "LOCAL_ONLY"
    export_supported = all(
        artifact.export_policy == "LOCAL_ONLY" for artifact in inputs.verified_artifacts
    )
    source_supported = (
        inputs.native_baseline.tool_name == _SUPPORTED_NATIVE_TOOL
        and inputs.native_baseline.tool_version.startswith(_SUPPORTED_PYTORCH_PREFIXES)
    )
    original = inputs.original_experiment_economics
    proposed = inputs.proposed_experiment_economics
    original_cost = original.estimated_cost
    proposed_cost = proposed.estimated_cost
    comparable = (
        original_cost is not None
        and proposed_cost is not None
        and original.currency == proposed.currency
    )
    if not comparable or original_cost is None or proposed_cost is None:
        economics_outcome = VerificationOutcome.UNKNOWN
    elif proposed_cost > original_cost:
        economics_outcome = VerificationOutcome.DENIED
    else:
        economics_outcome = VerificationOutcome.VERIFIED
    economics_reason = (
        "Original and proposed cost are not both known in the same currency."
        if not comparable
        else "Proposed experiment costs more than the original run."
        if economics_outcome is VerificationOutcome.DENIED
        else "Proposed experiment cost does not exceed the original run cost."
    )
    return [
        _verification(
            PolicyName.PACK_FIT,
            VerificationOutcome.VERIFIED if pack_supported else VerificationOutcome.DENIED,
            {"caseId": case.case_id, "packCandidate": case.pack_candidate},
            "Pack is supported." if pack_supported else "Pack is outside the supported envelope.",
        ),
        _verification(
            PolicyName.LOCAL_EXECUTION_AUTHORITY,
            VerificationOutcome.VERIFIED if access_known else VerificationOutcome.UNKNOWN,
            {
                "baseline": inputs.baseline_environment.materialization_recipe_digest,
                "candidate": inputs.candidate_environment.materialization_recipe_digest,
            },
            (
                "Both environments have case-bound materialization recipes."
                if access_known
                else "Local execution access is not machine-verifiable."
            ),
        ),
        _verification(
            PolicyName.PRIVACY_POLICY,
            VerificationOutcome.VERIFIED if privacy_supported else VerificationOutcome.DENIED,
            {"caseId": case.case_id, "privacyPolicy": case.privacy_policy},
            "Privacy policy is local-only."
            if privacy_supported
            else "Privacy policy is unsupported.",
        ),
        _verification(
            PolicyName.EXPORT_POLICY,
            VerificationOutcome.VERIFIED if export_supported else VerificationOutcome.DENIED,
            [
                {"artifactId": item.artifact_id, "exportPolicy": item.export_policy}
                for item in inputs.verified_artifacts
            ],
            "All evidence remains local."
            if export_supported
            else "Evidence export is unsupported.",
        ),
        _verification(
            PolicyName.SOURCE_VERSION,
            VerificationOutcome.VERIFIED if source_supported else VerificationOutcome.DENIED,
            {
                "tool": inputs.native_baseline.tool_name,
                "version": inputs.native_baseline.tool_version,
            },
            "Native source version is supported."
            if source_supported
            else "Native source version is unsupported.",
        ),
        _verification(
            PolicyName.ECONOMICS,
            economics_outcome,
            {
                "original": original.model_dump(mode="json", by_alias=True),
                "proposed": proposed.model_dump(mode="json", by_alias=True),
            },
            economics_reason,
        ),
    ]


def evaluate_preflight(
    inputs: PreflightInputs,
    *,
    artifact_reader: Callable[[EvidenceArtifact], bytes],
) -> EligibilityDecision:
    """Evaluate bound evidence with zero human authority or unverifiable caller booleans."""
    identity_strength = _identity_strength(inputs)
    try:
        raw_verified = all(
            sha256_digest(artifact_reader(artifact)) == artifact.content_digest
            for artifact in inputs.verified_artifacts
        )
    except (OSError, ValueError):
        raw_verified = False
    if not raw_verified:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            TechnicalResult.INVALID_EVIDENCE,
            ["One or more case-bound artifact payloads failed local CAS verification."],
            [],
        )
    try:
        lifecycle_disagreement = lifecycle_disagreement_from_raw(
            inputs.native_baseline.artifacts, artifact_reader
        )
    except (FlightRecorderImportError, OSError, ValueError):
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            TechnicalResult.INVALID_EVIDENCE,
            ["Native lifecycle truth could not be recomputed from raw CAS evidence."],
            [],
        )
    expected_decision = NATIVE_SUFFICIENT_DECISION if lifecycle_disagreement else None
    expected_refs = (
        sorted(artifact.artifact_id for artifact in inputs.native_baseline.artifacts)
        if lifecycle_disagreement
        else []
    )
    expected_digest = (
        digest_json(
            {
                "caseId": inputs.native_baseline.case_id,
                "decision": expected_decision,
                "evidenceRefs": expected_refs,
                "policyVersion": "traincapsule-native-sufficiency-v1",
            }
        )
        if expected_decision is not None
        else None
    )
    if (
        inputs.native_baseline.decision_reached != expected_decision
        or inputs.native_baseline.decision_evidence_refs != expected_refs
        or inputs.native_baseline.decision_provenance_digest != expected_digest
    ):
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            TechnicalResult.INVALID_EVIDENCE,
            ["Native decision record does not match recomputed raw CAS lifecycle truth."],
            [],
        )
    verifications = _policy_verifications(inputs)
    denied = [
        result
        for result in verifications
        if result.outcome is VerificationOutcome.DENIED
        and result.policy is not PolicyName.ECONOMICS
    ]
    if denied:
        policy_names = {
            PolicyName.PRIVACY_POLICY,
            PolicyName.EXPORT_POLICY,
            PolicyName.LOCAL_EXECUTION_AUTHORITY,
        }
        outcome = (
            EligibilityOutcome.POLICY_BLOCKED
            if {item.policy for item in denied} & policy_names
            else EligibilityOutcome.OUTSIDE_SUPPORTED_ENVELOPE
        )
        return _decision(
            inputs,
            identity_strength,
            outcome,
            TechnicalResult.POLICY_BLOCKED,
            [f"Machine verification denied {item.policy.value}." for item in denied],
            [],
        )
    if inputs.evaluated_at > inputs.incident_case.decision_deadline:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.EXPIRED,
            ["The named customer decision deadline has passed."],
            [],
        )
    unknown = sorted(
        result.policy.value
        for result in verifications
        if result.outcome is VerificationOutcome.UNKNOWN
    )
    if unknown:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.UNKNOWN,
            ["One or more machine-verifiable preflight inputs are unknown."],
            unknown,
        )
    if inputs.native_baseline.decision_reached:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT,
            TechnicalResult.PASS,
            ["The complete native workflow already records a decision."],
            [],
        )
    if inputs.completeness_report.technical_result is not TechnicalResult.PASS:
        result = inputs.completeness_report.technical_result
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            result if result is TechnicalResult.INVALID_EVIDENCE else TechnicalResult.UNKNOWN,
            ["Qualification requires complete, valid, case-bound evidence."],
            [],
        )
    if identity_strength in {IdentityStrength.UNVERIFIED, IdentityStrength.CONFLICTING}:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.NEEDS_MORE_EVIDENCE,
            TechnicalResult.UNKNOWN,
            ["Identity is unverified or conflicting."],
            [],
        )
    economics = next(item for item in verifications if item.policy is PolicyName.ECONOMICS)
    if economics.outcome is VerificationOutcome.DENIED:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.TECHNICALLY_POSSIBLE_BUT_UNECONOMIC,
            TechnicalResult.PASS,
            ["The supplied, evidence-bound cost hypothesis is uneconomic."],
            [],
        )
    if identity_strength is not IdentityStrength.FULLY_VERIFIED:
        return _decision(
            inputs,
            identity_strength,
            EligibilityOutcome.UNKNOWN,
            TechnicalResult.UNKNOWN,
            ["Identity strength does not permit an evidence-only approval."],
            ["fully verified identity"],
        )
    return _decision(
        inputs,
        identity_strength,
        EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION,
        TechnicalResult.PASS,
        ["All evidence-bound machine prerequisites are explicitly verified."],
        [],
    )


def _decision(
    inputs: PreflightInputs,
    identity_strength: IdentityStrength,
    outcome: EligibilityOutcome,
    technical_result: TechnicalResult,
    reasons: list[str],
    unknowns: list[str],
) -> EligibilityDecision:
    decisions = {
        EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION: OperationalDecision.APPROVE_WITHIN_ENVELOPE,
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
        case_id=inputs.incident_case.case_id,
        input_digest=digest_json(inputs.model_dump(mode="json", by_alias=True)),
        workload_id=inputs.workload_identity.workload_id,
        baseline_environment_id=inputs.baseline_environment.environment_id,
        candidate_environment_id=inputs.candidate_environment.environment_id,
        evidence_refs=sorted(item.artifact_id for item in inputs.verified_artifacts),
        native_baseline_digest=digest_json(
            inputs.native_baseline.model_dump(mode="json", by_alias=True)
        ),
        policy_verifications=_policy_verifications(inputs),
        original_experiment_economics=inputs.original_experiment_economics,
        proposed_experiment_economics=inputs.proposed_experiment_economics,
        outcome=outcome,
        identity_strength=identity_strength,
        technical_result=technical_result,
        operational_decision=decisions[outcome],
        reasons=reasons,
        unknowns=unknowns,
        generated_at=inputs.evaluated_at,
    )
