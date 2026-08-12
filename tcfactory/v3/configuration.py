"""Validated V3 factory policy and executor configuration."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from tcfactory.util import sha256_file
from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import CommercialMaturity, EvidenceType
from tcfactory.v3.scheduler import SchedulerConfig
from tcfactory.yamlutil import load_yaml


class RepositoryPolicy(V3Model):
    base_branch: Literal["main"]
    release_mode: Literal["owner_directed_main_only"]
    direct_main_push: Literal[True]
    require_clean_base: bool
    candidate_manifest_required: Literal[True]


class ExecutionPolicy(V3Model):
    backend: str = Field(min_length=1)
    max_concurrent_mutating_sessions: int = Field(ge=1, le=4)
    max_concurrent_read_only_sessions: int = Field(ge=1, le=8)
    work_until_done: Literal[False]
    checkpoint_every_stage: Literal[True]
    preserve_candidate_on_failure: Literal[True]


class SourceOfTruthPolicy(V3Model):
    active_bundle: str
    manifest: str
    context_index: str
    integrity_gate: str


class RoadmapPolicy(V3Model):
    milestones: str
    work_items: str
    dispositions: str
    legacy_map: str
    completion_mode: Literal["milestone"]
    expansion_mode: Literal["proposal_only"]


class RuntimePolicy(V3Model):
    local_state_root_environment_variable: str = Field(min_length=1)
    single_instance_lock: Literal[True]
    hard_stuck_file: Literal["HARD_STUCK.json"]
    stop_file: Literal["STOP"]
    migration_complete_marker: Literal["MIGRATION_COMPLETE_V3.json"]
    supervisor_state_file: Literal["supervisor-state.json"]
    supervisor_lock_file: Literal["supervisor.lock"]
    redact_secrets: Literal[True]
    raw_customer_evidence_in_repository: Literal[False]


class ReleasePolicy(V3Model):
    publication_branch: Literal["main"]
    non_main_pushes_forbidden: Literal[True]
    pull_request_dependency_forbidden: Literal[True]
    monitor_hosted_main_checks: Literal[True]
    automatic_revert_and_quarantine: Literal[True]
    require_candidate_sha_match: Literal[True]


class OperatorPolicy(V3Model):
    zero_human_operation: Literal[True]
    policy_gate_mode: Literal["deterministic_machine_policy"]
    owner_directed_deviation_record: str = Field(min_length=1)
    external_truth_remains_receipt_bound: Literal[True]
    synthetic_commercial_evidence_forbidden: Literal[True]


class FactoryV3Config(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    allow_paid_usage: Literal[False] = False
    repository: RepositoryPolicy
    execution: ExecutionPolicy
    source_of_truth: SourceOfTruthPolicy
    roadmap: RoadmapPolicy
    runtime: RuntimePolicy
    release: ReleasePolicy
    operator_policy: OperatorPolicy


class OwnerDirectives(V3Model):
    version: Literal[3]
    authority: Literal["repository_owner"]
    recorded_at: datetime
    directives: dict[str, object]
    safety_contract: dict[str, object]
    deviations_from_bundle: list[dict[str, str]]

    @model_validator(mode="after")
    def require_unattended_main_only(self) -> OwnerDirectives:
        required = {
            "unattendedOperation": "REQUIRED",
            "humanIntervention": "FORBIDDEN",
            "publicationBranch": "main",
            "nonMainPushes": "FORBIDDEN",
            "pullRequestDependency": "FORBIDDEN",
            "externalEvidencePolicy": "NEVER_FABRICATE",
            "missingEvidenceResult": "UNKNOWN",
            "scopedBlockersDoNotStopIndependentLanes": True,
        }
        if self.directives != required:
            raise ValueError("owner directives differ from the exact unattended main-only contract")
        pre = self.safety_contract.get("prePromotion")
        post = self.safety_contract.get("postPush")
        if not isinstance(pre, dict) or not all(
            cast(dict[str, object], pre).get(name) is True
            for name in (
                "requireExactCandidateSha",
                "requireDeterministicLocalGates",
                "requirePrivateGatesWhenConfigured",
                "requireMachinePolicyReceipt",
            )
        ):
            raise ValueError("owner pre-promotion safety contract is incomplete")
        if not isinstance(post, dict) or not all(
            cast(dict[str, object], post).get(name) is True
            for name in (
                "monitorRequiredMainChecks",
                "autoRevertFailedPromotion",
                "quarantineFailedCandidate",
                "finiteRetryBudgetRequired",
            )
        ):
            raise ValueError("owner post-push safety contract is incomplete")
        return self


class OwnerOverridePolicy(V3Model):
    version: Literal[3]
    decision_id: Literal["OWNER-ZERO-HUMAN-20260811"]
    authority: Literal["explicit repository owner direction in Codex task"]
    effective_date: Literal["2026-08-11"]
    decision: str = Field(min_length=1)
    replaces: list[str] = Field(min_length=1)
    machine_replacement: list[str] = Field(min_length=1)
    publication_policy: dict[str, str]
    unchanged_truth_boundaries: list[str] = Field(min_length=1)
    canonical_owner_directives: Literal["config/owner_directives.yaml"]
    canonical_owner_directives_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValidatedRuntimeSource(V3Model):
    version: Literal[3] = 3
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContextRoutingConfig(V3Model):
    version: Literal[3]
    default_max_context_characters: int = Field(ge=1, le=200_000)
    max_sources_per_manifest: int = Field(ge=1, le=16)
    require_entry_digest: Literal[True]
    require_authority_sections: Literal[True]
    reject_role_mismatch: Literal[True]
    reject_stale_current_facts: Literal[True]
    role_default_groups: dict[str, list[str]] = Field(min_length=1)


class DisabledHumanApprovalConfig(V3Model):
    version: Literal[3]
    enabled: Literal[False]
    runtime_states: list[str] = Field(max_length=0)
    trusted_root_environment_variable: None
    replacement: Literal["OWNER_DIRECTED_MACHINE_POLICY_RECEIPT"]
    missing_policy_disposition: Literal["BLOCKED_POLICY"]
    external_fact_disposition: Literal["WAITING_EXTERNAL"]
    fabrication_forbidden: Literal[True]


class PlanningAutonomy(V3Model):
    auto_plan: bool
    max_plan_attempts: int = Field(ge=1, le=5)
    max_acceptance_criteria: int = Field(ge=1, le=12)
    max_expected_outputs: int = Field(ge=1, le=8)
    max_context_documents: int = Field(ge=1, le=8)
    reuse_valid_plans: bool


class CandidateAutonomy(V3Model):
    max_candidate_repair_cycles: int = Field(ge=1, le=10)
    max_same_finding_repeats: int = Field(ge=1, le=5)
    max_candidate_restarts: int = Field(ge=1, le=3)
    preserve_on_exhaustion: Literal[True]


class RecoveryAutonomy(V3Model):
    auto_resume_quota: bool
    auto_recover_interrupted: bool
    max_infrastructure_recoveries_per_run: int = Field(ge=1, le=10)
    max_factory_self_repairs_per_incident: int = Field(ge=1, le=3)
    max_controller_restarts: Literal[3]
    restart_backoff_seconds: tuple[Literal[15], Literal[60], Literal[300]]
    require_healthy_seconds_to_reset_restart_budget: int = Field(ge=60)

    @model_validator(mode="after")
    def finite_backoff(self) -> RecoveryAutonomy:
        if self.restart_backoff_seconds != (15, 60, 300):
            raise ValueError("controller restart backoff must be exactly 15, 60, and 300 seconds")
        return self


class ValueAutonomy(V3Model):
    max_value_redesigns: int = Field(ge=1, le=3)
    stop_on_native_workflow_sufficient: Literal[True]
    stop_on_no_incremental_decision_value: Literal[True]
    stop_on_technically_valid_but_uneconomic: Literal[True]


class CompletionAutonomy(V3Model):
    max_expansion_rounds_per_milestone: int = Field(ge=1, le=2)
    max_expansion_items: int = Field(ge=1, le=5)
    roadmap_expansion_requires_machine_policy_receipt: Literal[True]
    reviewers_may_mutate_roadmap: Literal[False]


class ExternalAutonomy(V3Model):
    ai_may_complete_external_evidence: Literal[False]
    machine_policy_receipts_required: Literal[True]
    synthetic_evidence_may_advance_commercial_maturity: Literal[False]


class AutonomyV3Config(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    enabled: bool = False
    allow_paid_usage: Literal[False] = False
    planning: PlanningAutonomy
    candidate: CandidateAutonomy
    recovery: RecoveryAutonomy
    value: ValueAutonomy
    completion: CompletionAutonomy
    external: ExternalAutonomy


class ExecutorBackend(V3Model):
    adapter: str = Field(min_length=1)
    authentication: Literal["subscription", "local", "test"]
    enabled: bool
    max_concurrent_sessions: int = Field(ge=1, le=8)
    capabilities: list[str]
    durable_state_owned_by_factory: Literal[True]


class ExecutorConfig(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    default_backend: str = Field(min_length=1)
    allow_paid_usage: Literal[False] = False
    backends: dict[str, ExecutorBackend]
    weekly_allocation_percent: dict[str, int]
    priority_under_pressure: list[str]

    @model_validator(mode="after")
    def validate_executor_allocation(self) -> ExecutorConfig:
        backend = self.backends.get(self.default_backend)
        if backend is None or not backend.enabled:
            raise ValueError("default executor backend must exist and be enabled")
        if sum(self.weekly_allocation_percent.values()) != 100:
            raise ValueError("weekly executor allocation must total 100 percent")
        if any(value < 0 for value in self.weekly_allocation_percent.values()):
            raise ValueError("weekly executor allocation cannot be negative")
        return self


class ExternalEvidenceConfig(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    trusted_root_environment_variable: str = Field(min_length=1)
    trusted_public_key_environment_variable: str = Field(min_length=1)
    allow_repository_fallback: Literal[False]
    receipt_schema: str
    require_signature: Literal[True]
    agent_writable: Literal[False]
    allowed_evidence_types: list[EvidenceType]


class CommercialMaturityConfig(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    synthetic_evidence_may_advance: Literal[False]
    repository_authored_receipts_are_trusted: Literal[False]
    evidence_requirements: dict[CommercialMaturity, list[EvidenceType]]

    @model_validator(mode="after")
    def complete_maturity_policy(self) -> CommercialMaturityConfig:
        if set(self.evidence_requirements) != set(CommercialMaturity):
            raise ValueError("commercial maturity evidence policy is incomplete")
        return self


class MilestonePolicyConfig(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    active_milestone: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    roadmap_path: str
    completion_mode: Literal["milestone"]
    expansion_mode: Literal["proposal_only"]
    source_migration_machine_policy_receipt_required: Literal[True]
    external_milestones: list[str]


def load_factory_v3(path: Path) -> FactoryV3Config:
    return FactoryV3Config.model_validate(load_yaml(path))


def load_autonomy_v3(path: Path) -> AutonomyV3Config:
    return AutonomyV3Config.model_validate(load_yaml(path))


def load_scheduler_v3(path: Path) -> SchedulerConfig:
    return SchedulerConfig.model_validate(load_yaml(path))


def load_executors_v3(path: Path) -> ExecutorConfig:
    return ExecutorConfig.model_validate(load_yaml(path))


PROTECTED_ENVIRONMENT_OVERRIDES = frozenset(
    {
        "TCF_RELEASE_MODE",
        "TCF_AUTO_MERGE",
        "TCF_RECEIPT_TRUST_ROOT_OVERRIDE",
        "TCF_PRIVATE_GATE_RUNNER",
        "TCF_ALLOW_UNSANDBOXED",
        "TCF_DISABLE_KILL_GATES",
        "TCF_MAX_PARALLEL",
    }
)


def validate_v3_configuration(repo_root: Path) -> dict[str, V3Model]:
    """Validate the complete V3 configuration set and reject protected overrides."""

    present = sorted(name for name in PROTECTED_ENVIRONMENT_OVERRIDES if os.getenv(name))
    if present:
        raise ValueError(f"protected V3 environment overrides are forbidden: {present}")
    owner_directives_path = repo_root / "config/owner_directives.yaml"
    override_path = repo_root / "factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json"
    owner_directives = OwnerDirectives.model_validate(load_yaml(owner_directives_path))
    from tcfactory.claude_features import load_claude_features
    from tcfactory.config import load_roles
    from tcfactory.github_sync import load_github_config
    from tcfactory.risk import load_risk_profiles
    from tcfactory.util import read_json

    roles = load_roles(repo_root / "config/roles.yaml")
    claude_features = load_claude_features(repo_root / "config/claude_features.yaml")
    risk_profiles = load_risk_profiles(repo_root / "config/risk_profiles.yaml")
    if claude_features.version != 3 or risk_profiles.get("version") != 3:
        raise ValueError("Claude feature and risk configuration must declare version 3")
    load_github_config(repo_root / "config/github.yaml")
    context_index = load_yaml(repo_root / "docs/CONTEXT_INDEX.yaml")
    if context_index.get("version") != 3 or not isinstance(context_index.get("groups"), dict):
        raise ValueError("V3 context index is missing or invalid")
    override = OwnerOverridePolicy.model_validate(read_json(override_path, {}))
    if override.canonical_owner_directives_sha256 != sha256_file(owner_directives_path):
        raise ValueError("owner override policy does not match canonical owner directives")
    context_policy = ContextRoutingConfig.model_validate(
        load_yaml(repo_root / "config/context.yaml")
    )
    groups = cast(dict[str, object], context_index["groups"])
    configured_roles = {role.value for role in roles}
    if set(context_policy.role_default_groups) != configured_roles:
        raise ValueError("context role defaults must exactly match configured roles")
    for role, group_names in context_policy.role_default_groups.items():
        if not 0 < len(group_names) <= context_policy.max_sources_per_manifest:
            raise ValueError(f"context defaults exceed bounded group count for role {role}")
        for group_name in group_names:
            raw_group = groups.get(group_name)
            if not isinstance(raw_group, dict):
                raise ValueError(f"unknown context group for role {role}: {group_name}")
            group = cast(dict[str, object], raw_group)
            include = group.get("includeRoles")
            exclude = group.get("excludeRoles")
            if not isinstance(include, list) or role not in include or (
                isinstance(exclude, list) and role in exclude
            ):
                raise ValueError(f"context group {group_name} is not authorized for role {role}")
    loaded: dict[str, V3Model] = {
        "factory": load_factory_v3(repo_root / "config/factory.yaml"),
        "autonomy": load_autonomy_v3(repo_root / "config/autonomy.yaml"),
        "scheduler": load_scheduler_v3(repo_root / "config/scheduler.yaml"),
        "executors": load_executors_v3(repo_root / "config/executors.yaml"),
        "externalEvidence": ExternalEvidenceConfig.model_validate(
            load_yaml(repo_root / "config/external_evidence.yaml")
        ),
        "commercialMaturity": CommercialMaturityConfig.model_validate(
            load_yaml(repo_root / "config/commercial_maturity.yaml")
        ),
        "milestones": MilestonePolicyConfig.model_validate(
            load_yaml(repo_root / "config/milestones.yaml")
        ),
        "contextPolicy": context_policy,
        "humanApprovalDisabled": DisabledHumanApprovalConfig.model_validate(
            load_yaml(repo_root / "config/human_approval.yaml")
        ),
        "ownerDirectives": owner_directives,
        "ownerOverridePolicy": override,
    }
    for name, relative in {
        "github": "config/github.yaml",
        "roles": "config/roles.yaml",
        "contextIndex": "docs/CONTEXT_INDEX.yaml",
        "riskProfiles": "config/risk_profiles.yaml",
        "claudeFeatures": "config/claude_features.yaml",
    }.items():
        loaded[name] = ValidatedRuntimeSource(
            path=relative, sha256=sha256_file(repo_root / relative)
        )
    versions = {int(cast(Any, value).version) for value in loaded.values()}
    if versions != {3}:
        raise ValueError(f"mixed or legacy normal-operation configuration: {sorted(versions)}")
    return loaded


def explain_v3_config_field(repo_root: Path, dotted_field: str) -> dict[str, object]:
    """Explain a field and its exact file provenance; no protected env overlay exists."""

    if not dotted_field or dotted_field.startswith(".") or dotted_field.endswith("."):
        raise ValueError("config field must be a dotted path")
    root_name, *parts = dotted_field.split(".")
    loaded = validate_v3_configuration(repo_root)
    if root_name not in loaded:
        raise KeyError(root_name)
    value: object = loaded[root_name].model_dump(mode="json", by_alias=True)
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted_field)
        value = cast(dict[str, object], value)[part]
    file_names = {
        "factory": "factory.yaml",
        "autonomy": "autonomy.yaml",
        "scheduler": "scheduler.yaml",
        "executors": "executors.yaml",
        "externalEvidence": "external_evidence.yaml",
        "commercialMaturity": "commercial_maturity.yaml",
        "milestones": "milestones.yaml",
        "ownerDirectives": "owner_directives.yaml",
    }
    return {
        "field": dotted_field,
        "value": value,
        "source": str(repo_root / "config" / file_names[root_name]),
        "environmentOverride": None,
        "protected": dotted_field.startswith(
            (
                "factory.repository.releaseMode",
                "factory.release",
                "factory.runtime",
                "externalEvidence",
            )
        ),
    }
