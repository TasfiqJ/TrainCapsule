"""Validated V3 factory policy and executor configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from tcfactory.util import sha256_file
from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import CommercialMaturity, EvidenceType
from tcfactory.v3.scheduler import SchedulerConfig
from tcfactory.v3.source_authority import (
    ActiveGenerationConfig,
    validate_active_source_generation,
)
from tcfactory.yamlutil import load_yaml


class RepositoryPolicy(V3Model):
    base_branch: Literal["main"]
    release_mode: Literal["DIRECT_MAIN_EXACT_SHA_MACHINE_RECEIPT_POST_PUSH_VERIFY"]
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
    active_generation: Literal["config/active_generation.yaml"]
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
    direct_main_push_forbidden: Literal[False]
    automated_pull_request_required: Literal[False]
    exact_head_sha_checks_required: Literal[True]
    independent_machine_policy_receipt_required: Literal[True]
    merge_queue_or_auto_merge_required: Literal[False]
    exact_merged_main_verification_required: Literal[True]
    publisher_capability: Literal["DIRECT_MAIN_V31_READY"]


class OperatorPolicy(V3Model):
    zero_human_operation: Literal[True]
    policy_gate_mode: Literal["deterministic_machine_policy"]
    active_authority_manifest: Literal[
        "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json"
    ]
    external_truth_remains_receipt_bound: Literal[True]
    synthetic_commercial_evidence_forbidden: Literal[True]


class LegacyConfigCompatibility(V3Model):
    input_version: Literal[3]
    disposition: Literal["READ_ONLY_LOSSLESS_ADAPTER"]
    allowed_inputs: list[str] = Field(min_length=1)
    reject_undeclared_inputs: Literal[True]


class FactoryV3Config(V3Model):
    schema_version: Literal["3.1"]
    generation_id: Literal["traincapsule-v3.1-zh-2026-08-12"]
    allow_paid_usage: Literal[False] = False
    repository: RepositoryPolicy
    execution: ExecutionPolicy
    source_of_truth: SourceOfTruthPolicy
    roadmap: RoadmapPolicy
    runtime: RuntimePolicy
    release: ReleasePolicy
    operator_policy: OperatorPolicy
    compatibility: LegacyConfigCompatibility


class ValidatedRuntimeSource(V3Model):
    schema_version: Literal["3.1"] = "3.1"
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
    # The protected V3/V3.1-ZH contract permits exactly one bounded expansion
    # round.  Keeping this as a Literal prevents a locally supplied value of
    # two from widening policy beyond the completion evaluator's hard stop.
    max_expansion_rounds_per_milestone: Literal[1]
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
    from tcfactory.claude_features import load_claude_features
    from tcfactory.config import load_roles
    from tcfactory.github_sync import load_github_config
    from tcfactory.risk import load_risk_profiles

    roles = load_roles(repo_root / "config/roles.yaml")
    claude_features = load_claude_features(repo_root / "config/claude_features.yaml")
    risk_profiles = load_risk_profiles(repo_root / "config/risk_profiles.yaml")
    if claude_features.version != 3 or risk_profiles.get("version") != 3:
        raise ValueError("Claude feature and risk configuration must declare version 3")
    github = load_github_config(repo_root / "config/github.yaml")
    context_index = load_yaml(repo_root / "docs/CONTEXT_INDEX.yaml")
    if context_index.get("version") != 4 or not isinstance(context_index.get("groups"), dict):
        raise ValueError("V3.1-ZH context index is missing or invalid")
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
            if (
                not isinstance(include, list)
                or role not in include
                or (isinstance(exclude, list) and role in exclude)
            ):
                raise ValueError(f"context group {group_name} is not authorized for role {role}")
    factory = load_factory_v3(repo_root / "config/factory.yaml")
    active_source = validate_active_source_generation(repo_root)
    active_generation = ActiveGenerationConfig.model_validate(
        load_yaml(repo_root / factory.source_of_truth.active_generation)
    )
    if factory.source_of_truth.active_bundle != active_source.source_root or (
        factory.source_of_truth.manifest != active_source.manifest_path
    ):
        raise ValueError("factory source paths differ from the canonical active generation")
    loaded: dict[str, V3Model] = {
        "factory": factory,
        "activeGeneration": active_generation,
        "activeSource": active_source,
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
        "github": github,
    }
    for name, relative in {
        "roles": "config/roles.yaml",
        "contextIndex": "docs/CONTEXT_INDEX.yaml",
        "riskProfiles": "config/risk_profiles.yaml",
        "claudeFeatures": "config/claude_features.yaml",
    }.items():
        loaded[name] = ValidatedRuntimeSource(
            path=relative, sha256=sha256_file(repo_root / relative)
        )
    compatibility_inputs = {
        "autonomy": "config/autonomy.yaml",
        "scheduler": "config/scheduler.yaml",
        "executors": "config/executors.yaml",
        "externalEvidence": "config/external_evidence.yaml",
        "commercialMaturity": "config/commercial_maturity.yaml",
        "milestones": "config/milestones.yaml",
        "contextPolicy": "config/context.yaml",
    }
    if set(factory.compatibility.allowed_inputs) != set(compatibility_inputs.values()):
        raise ValueError("V3 compatibility inputs differ from the explicit lossless adapter set")
    legacy_versions = {name: cast(Any, loaded[name]).version for name in compatibility_inputs}
    if set(legacy_versions.values()) != {factory.compatibility.input_version}:
        raise ValueError(f"legacy compatibility input version mismatch: {legacy_versions}")
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
        "activeGeneration": "active_generation.yaml",
    }
    return {
        "field": dotted_field,
        "value": value,
        "source": (
            str(repo_root / "config" / file_names[root_name])
            if root_name in file_names
            else str(repo_root / "config/active_generation.yaml")
        ),
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
