"""Validated V3 factory policy and executor configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import CommercialMaturity, EvidenceType
from tcfactory.v3.scheduler import SchedulerConfig
from tcfactory.yamlutil import load_yaml


class RepositoryPolicy(V3Model):
    base_branch: Literal["main"]
    release_mode: Literal["pull_request"]
    direct_main_push: Literal[False]
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
    hard_stuck_file: str = Field(min_length=1)
    redact_secrets: Literal[True]
    raw_customer_evidence_in_repository: Literal[False]


class ReleasePolicy(V3Model):
    create_draft_pull_request: Literal[True]
    auto_merge_mechanical: Literal[False]
    auto_merge_standard: Literal[False]
    auto_merge_integration: Literal[False]
    auto_merge_trust_core: Literal[False]
    require_candidate_sha_match: Literal[True]


class FactoryV3Config(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    allow_paid_usage: Literal[False] = False
    repository: RepositoryPolicy
    execution: ExecutionPolicy
    source_of_truth: SourceOfTruthPolicy
    roadmap: RoadmapPolicy
    runtime: RuntimePolicy
    release: ReleasePolicy


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
    max_controller_restarts: int = Field(ge=1, le=10)
    restart_backoff_seconds: list[int] = Field(min_length=1, max_length=5)
    require_healthy_seconds_to_reset_restart_budget: int = Field(ge=60)

    @model_validator(mode="after")
    def finite_backoff(self) -> RecoveryAutonomy:
        if any(value <= 0 for value in self.restart_backoff_seconds):
            raise ValueError("restart backoff values must be positive")
        if self.restart_backoff_seconds != sorted(self.restart_backoff_seconds):
            raise ValueError("restart backoff values must be nondecreasing")
        return self


class ValueAutonomy(V3Model):
    max_value_redesigns: int = Field(ge=1, le=3)
    stop_on_native_workflow_sufficient: Literal[True]
    stop_on_no_incremental_decision_value: Literal[True]
    stop_on_technically_valid_but_uneconomic: Literal[True]


class CompletionAutonomy(V3Model):
    max_expansion_rounds_per_milestone: int = Field(ge=1, le=2)
    max_expansion_items: int = Field(ge=1, le=5)
    roadmap_expansion_requires_human_approval: Literal[True]
    reviewers_may_mutate_roadmap: Literal[False]


class ExternalAutonomy(V3Model):
    ai_may_complete_external_evidence: Literal[False]
    ai_may_complete_human_review: Literal[False]
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
    source_migration_approval_required: Literal[True]
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
        "TCF_HUMAN_APPROVAL_ROOT_OVERRIDE",
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
    }
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
