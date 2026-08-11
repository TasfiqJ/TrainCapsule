# ruff: noqa: E501
from __future__ import annotations

from .models import (
    RiskTier,
    RoleName,
    Stage,
    TaskPacket,
)

# Objective contract strings are intentionally kept as complete prompt sentences.


REVIEW_ROLES = {
    RoleName.INTEGRATION_SCOUT,
    RoleName.ADVERSARY,
    RoleName.AUDIT,
    RoleName.SECURITY,
    RoleName.PERFORMANCE,
    RoleName.VALUE_VALIDATOR,
    RoleName.VALUE_ADVERSARY,
    RoleName.RELEASE,
    RoleName.COMPLETION_AUDIT,
    RoleName.COMPLETION_ADJUDICATOR,
}


# Product-task agents must never rewrite controller policy, authority, private gates,
# or durable controller state.  Keep this baseline in a dependency-light module so
# planning and runtime repair routing classify the same paths.
PRODUCT_PROTECTED_PATHS = frozenset(
    {
        ".claude/**",
        "config/**",
        "prompts/**",
        "tcfactory/**",
        "schemas/**",
        "factory/state/**",
        "factory/queue/**",
        "factory/feature_ledger.yaml",
        "factory/product_definition_of_done.yaml",
        "factory/task_catalog.yaml",
        "docs/source-of-truth/**",
        "docs/CONTEXT_INDEX.yaml",
        "config/risk_profiles.yaml",
        "config/context.yaml",
        "config/github.yaml",
        "scripts/gates/**",
        "Control-TrainCapsuleBuilder.ps1",
        "Install-TrainCapsuleAutonomousBuilder.ps1",
        "bootstrap/private-gates/**",
    }
)

COMMON_OBJECTIVE_CRITERIA = (
    "Bind every conclusion to the exact candidate SHA, authoritative source, acceptance-criterion ID, and independently inspectable evidence path or command.",
    "Classify authority gaps and unsupported conclusions as UNKNOWN or BLOCKED; confidence, polish, file presence, and test count are never evidence by themselves.",
    "Assess correctness/truth, real user outcome, failure and recovery, security/privacy, operability/support, adoption friction, and commercial truth; mark a dimension not applicable only with a task-specific reason.",
    "Report exact limitations, residual risks, and the next falsifiable action without claiming external adoption, payment, retention, or demand from synthetic or self-authored evidence.",
)

ROLE_OBJECTIVE_CRITERIA: dict[RoleName, tuple[str, ...]] = {
    RoleName.PLANNER: (
        "Exit with a traceable outcome contract naming the target user/buyer, painful job, user-visible result, causal mechanism, parent sellable milestone, predeclared metric/threshold, and falsifiers.",
        "Give every acceptance criterion a stable ID and map it to source path/section, observable behavior or truth state, output, authorized owner, deterministic gate, evidence class, and independent oracle.",
        "Prove plan feasibility: every source anchor exists, every output is writable, required tools/network are available, gates are controller-safe, and protected or private oracles are independent.",
    ),
    RoleName.SPECIFICATION: (
        "Freeze a criterion-to-contract matrix that separates normative, inferred, optional, and UNKNOWN behavior before implementation.",
        "Specify interfaces, state/status transitions, invariants, errors, security/privacy boundaries, observability, compatibility, performance, accessibility, operations, support, upgrade, rollback, and stop rules where applicable.",
        "Define executable positive, negative, boundary, integration, recovery, and mutation evidence for every critical criterion without copying the candidate implementation into its oracle.",
    ),
    RoleName.RESEARCH: (
        "Pre-register the decision, expected subject/finding IDs, claim boundaries, source adapters/endpoints, query and request-shape fingerprints, freshness window, controls, falsifiers, and per-verdict downstream actions before collecting evidence.",
        "Preserve sanitized raw request/response metadata, status, timestamp, tool/adapter version, source class, candidate SHA, artifact hash, and reproduction method for every target and control execution.",
        "Complete every expected finding and derive the overall conclusion mechanically; research-process PASS is distinct from substantive CLEAR, CONFLICT, or UNKNOWN.",
    ),
    RoleName.BUILDER: (
        "Map every acceptance-criterion ID to the changed product boundary and to executable evidence; do not substitute documentation, scaffolding, mocks, or generated prose for required behavior.",
        "Exercise the real supported user journey plus negative, boundary, integration, diagnostic, and recovery paths; preserve explicit truth states and independent oracle lineage.",
        "Finish the in-scope install/configuration, onboarding/first value, reliability, observability, support, packaging, upgrade/rollback, accessibility, and privacy-safe measurement surfaces needed for a production outcome.",
    ),
    RoleName.INTEGRATION_SCOUT: (
        "Independently enumerate boundary assumptions, versions, real upstream paths, state/provenance handoffs, and failure propagation before accepting the builder's integration claim.",
        "Block only with a concrete reproducible counterexample tied to an exact path/symbol and candidate SHA; distinguish unavailable evidence from a product defect.",
    ),
    RoleName.ADVERSARY: (
        "Blindly challenge every applicable production dimension: criterion truth, real integrations, install and first value, repeated use, diagnostics and recovery, upgrade and rollback, security and privacy, representative performance, operability, support, accessibility, and material-value evidence.",
        "Attempt executable false-green counterexamples for status laundering, omitted subjects, circular oracles, weakened tests, mocks, corrupted evidence, malicious inputs, resource exhaustion, synthetic commercial claims, and missing failure/recovery paths.",
        "Every observation must use structured review_findings with blocking, severity, criterion ID, owner class, exact repair paths, failing command or artifact, and counterexample; advisory citations cannot control repair routing.",
    ),
    RoleName.AUDIT: (
        "Produce an independent criterion-to-evidence matrix and recompute claims, hashes, provenance, status arithmetic, gate identity, source authority, and candidate-SHA binding.",
        "Sample or reproduce real boundaries and controls; a prior reviewer verdict is evidence to challenge, never an oracle to copy.",
    ),
    RoleName.SECURITY: (
        "Threat-model trust boundaries, identities, secrets, dependencies, data lifecycle, tenant/privacy isolation, untrusted input, path/archive/shell/network abuse, denial of service, and containment failure.",
        "Back every PASS with negative tests or reproducible controls and disclose residual risk, severity, exploit preconditions, and exact remediation ownership.",
    ),
    RoleName.PERFORMANCE: (
        "Use a predeclared representative workload, baseline, threshold, resource budget, environment, candidate SHA, repetitions, and raw results; separate product regressions from measurement noise.",
        "Test pathological inputs and sustained operation, and never turn synthetic throughput or latency into customer-demand evidence.",
    ),
    RoleName.VALUE_VALIDATOR: (
        "Re-run the predeclared causal mechanism and verify baseline, materiality threshold, required conditions, evidence class, raw artifacts, candidate SHA, and falsification results.",
        "Separate deterministic technical/user value from external adoption, willingness to pay, retention, and demand, which remain externally attributable truth.",
    ),
    RoleName.VALUE_ADVERSARY: (
        "Attack metric choice, denominator, threshold timing, omitted workflow cost, synthetic evidence, tiny effects, replaceability, and the link from delivered behavior to the buyer's costly job.",
        "Return redesign with a falsifiable direction when the result works but is immaterial; never reward polish or roadmap motion.",
    ),
    RoleName.RELEASE: (
        "Verify the exact release SHA in a clean environment through install, onboarding/first value, normal operation, diagnostics, failure recovery, upgrade, rollback, backup/restore, and supported removal where applicable.",
        "Reconcile artifact hashes, deterministic/private/value gates, CI identity, user-visible limitations, compatibility, security/privacy, support evidence, and every acceptance-criterion ID before promotion.",
    ),
    RoleName.RECOVERY: (
        "Reproduce and classify the root cause, preserve valid candidate work, repair only the authorized surface, add a regression, and prove pause/resume plus exactly-one-controller recovery.",
        "Never make a product failure green by weakening gates, truth states, protected expectations, source authority, security, or spending controls.",
    ),
    RoleName.FACTORY_REPAIR: (
        "Reproduce the controller defect independently, identify its exact causal path and affected pipeline state, implement the smallest complete controller repair, and add a regression that fails before the fix.",
        "Run factory quality/security/spending/self-repair gates, preserve the product candidate, and emit a verified retry artifact before resuming exactly one controller.",
    ),
    RoleName.COMPLETION_AUDIT: (
        "Blindly audit every product-definition-of-done criterion against executable evidence from the exact main SHA across user outcome, truth, reliability, security/privacy, operability/support, adoption readiness, and commercial truth.",
        "Convert every missing capability into a bounded dependency-aware work item; never infer completion from roadmap status, file presence, or another auditor's verdict.",
    ),
    RoleName.COMPLETION_ADJUDICATOR: (
        "Reconcile independent audit disagreements criterion by criterion using executable evidence, without averaging confidence or allowing one reviewer to anchor another.",
        "Complete only when all deterministic, private, release, and commercialization-readiness evidence is present and externally attributable claims remain truthfully external.",
    ),
}


def objective_stage_criteria(role: RoleName) -> list[str]:
    return [*COMMON_OBJECTIVE_CRITERIA, *ROLE_OBJECTIVE_CRITERIA.get(role, ())]


def apply_objective_stage_contracts(packet: TaskPacket) -> TaskPacket:
    stages: list[Stage] = []
    required_gates = [gate.name for gate in packet.gates if gate.required]
    for stage in packet.pipeline:
        criteria = list(
            dict.fromkeys([*stage.acceptance_criteria, *objective_stage_criteria(stage.role)])
        )
        machine_gates = list(stage.machine_gates)
        if not machine_gates and stage.role not in REVIEW_ROLES:
            machine_gates = required_gates
        stages.append(
            stage.model_copy(
                update={
                    "acceptance_criteria": criteria,
                    "machine_gates": machine_gates,
                }
            )
        )
    return packet.model_copy(update={"pipeline": stages})


def objective_pipeline_errors(packet: TaskPacket) -> list[str]:
    errors: list[str] = []
    roles = [stage.role for stage in packet.pipeline]
    if not roles:
        return ["pipeline must contain one Claude owner stage"]
    releases = [index for index, role in enumerate(roles) if role == RoleName.RELEASE]
    if releases and releases != [len(roles) - 1]:
        errors.append("a legacy model release stage must be unique and last")

    first_review = next(
        (index for index, role in enumerate(roles) if role in REVIEW_ROLES), len(roles)
    )
    for index, stage in enumerate(packet.pipeline):
        if stage.role in REVIEW_ROLES:
            if stage.read_only is not True:
                errors.append(f"review stage {stage.role.value} must be read-only")
        elif index > first_review:
            errors.append(
                f"mutating stage {stage.role.value} cannot run after independent review begins"
            )
        if (
            stage.role not in REVIEW_ROLES
            and stage.read_only is not True
            and not stage.allowed_paths
        ):
            errors.append(f"writable stage {stage.role.value} has no allowed paths")
        if not stage.machine_gates and stage.role not in REVIEW_ROLES | {
            RoleName.COMPLETION_AUDIT,
            RoleName.COMPLETION_ADJUDICATOR,
        }:
            errors.append(f"stage {stage.role.value} has no deterministic machine gate")

    writable = [
        stage
        for stage in packet.pipeline
        if stage.role not in REVIEW_ROLES and stage.read_only is not True
    ]
    if len(writable) != 1:
        errors.append("pipeline must contain exactly one renewable Claude owner stage")

    required: set[RoleName] = set()
    if packet.risk_tier != RiskTier.MECHANICAL and not packet.task_id.startswith("PLAN_"):
        required.add(RoleName.ADVERSARY)
    missing = sorted(role.value for role in required - set(roles))
    if missing:
        errors.append("pipeline is missing required objective stages: " + ", ".join(missing))

    if (
        RoleName.ADVERSARY in roles
        and RoleName.AUDIT in roles
        and roles.index(RoleName.ADVERSARY) > roles.index(RoleName.AUDIT)
    ):
        errors.append("adversary must run before audit")
    if (
        RoleName.VALUE_VALIDATOR in roles
        and RoleName.VALUE_ADVERSARY in roles
        and roles.index(RoleName.VALUE_VALIDATOR) > roles.index(RoleName.VALUE_ADVERSARY)
    ):
        errors.append("value validator must run before value adversary")
    return errors
