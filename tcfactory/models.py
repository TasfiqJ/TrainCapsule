from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]
PermissionMode = Literal["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"]


class RiskTier(StrEnum):
    MECHANICAL = "mechanical"
    STANDARD = "standard"
    INTEGRATION = "integration"
    TRUST_CORE = "trust_core"


class ValueGateMode(StrEnum):
    """How a roadmap task must prove that it contributes meaningful product value."""

    FOUNDATIONAL = "foundational"
    MEASURED = "measured"
    EXTERNAL = "external"
    NOT_REQUIRED = "not_required"


class MetricDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    BINARY = "binary"
    EXTERNAL = "external"


class ValueStatus(StrEnum):
    PASS = "pass"
    REDESIGN = "redesign"
    FAIL = "fail"
    UNKNOWN = "unknown"
    EXTERNAL_EVIDENCE_REQUIRED = "external_evidence_required"


class ValueEvidenceClass(StrEnum):
    DETERMINISTIC = "deterministic_measurement"
    CONTROLLED = "controlled_experiment"
    UPSTREAM = "upstream_behavior"
    EXTERNAL_USAGE = "external_usage"
    PAID = "paid_revealed_preference"
    FOUNDATIONAL = "foundational_dependency"


class CommitType(StrEnum):
    FEAT = "feat"
    FIX = "fix"
    TEST = "test"
    DOCS = "docs"
    CHORE = "chore"
    REFACTOR = "refactor"
    PERF = "perf"
    BUILD = "build"
    CI = "ci"
    SPEC = "spec"


class RoleName(StrEnum):
    PLANNER = "planner"
    SPECIFICATION = "specification"
    BUILDER = "builder"
    ADVERSARY = "adversary"
    AUDIT = "audit"
    SECURITY = "security"
    PERFORMANCE = "performance"
    RELEASE = "release"
    RESEARCH = "research"
    RECOVERY = "recovery"
    FACTORY_REPAIR = "factory_repair"
    COMPLETION_AUDIT = "completion_audit"
    COMPLETION_ADJUDICATOR = "completion_adjudicator"
    VALUE_VALIDATOR = "value_validator"
    VALUE_ADVERSARY = "value_adversary"
    INTEGRATION_SCOUT = "integration_scout"


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class PauseKind(StrEnum):
    FIVE_HOUR = "five_hour_limit"
    WEEKLY = "weekly_limit"
    MODEL_LIMIT = "model_limit"
    TRANSIENT_RATE_LIMIT = "transient_rate_limit"
    SERVICE_CAPACITY = "service_capacity"
    AUTHENTICATION = "authentication"
    UNKNOWN_LIMIT = "unknown_limit"


class PipelineState(StrEnum):
    NEW = "new"
    RUNNING = "running"
    PAUSED = "paused"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class QueueState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


class Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    timeout_seconds: int = Field(default=900, ge=1, le=7200)
    stages: list[RoleName] = Field(default_factory=list[RoleName])
    required: bool = True


class PrivateGate(BaseModel):
    """Reference to a gate whose implementation lives outside the agent-visible repository."""

    model_config = ConfigDict(extra="forbid")

    required: bool = False
    suite: str | None = None
    timeout_seconds: int = Field(default=1800, ge=1, le=14_400)

    @model_validator(mode="after")
    def required_gate_has_suite(self) -> PrivateGate:
        if self.required and not self.suite:
            raise ValueError("private_gate.suite is required when private_gate.required is true")
        return self


class Stage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleName
    model: str | None = None
    effort: EffortLevel | None = None
    max_turns: int | None = Field(default=None, ge=1, le=200)
    max_budget_usd: float | None = Field(default=None, gt=0)
    task_budget_tokens: int | None = Field(default=None, ge=1000)
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    permission_mode: PermissionMode | None = None
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_keys: list[str] = Field(default_factory=list)
    max_context_chars: int | None = Field(default=None, ge=10_000, le=2_000_000)
    machine_gates: list[str] = Field(default_factory=list)
    read_only: bool | None = None
    require_changes: bool | None = None
    # Claude-specific orchestration. These are controller-owned capabilities, not
    # permissions the model can self-enable.
    advisor_model: str | None = None
    peer_messaging: bool = False
    session_name: str | None = None
    goal_condition: str | None = None
    workflow_name: str | None = None


class RepairPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_cycles: int = Field(default=2, ge=0, le=5)
    builder_models: list[str] = Field(default_factory=lambda: ["sonnet", "opus"])
    mutating_retry_models: list[str] = Field(default_factory=list)
    restart_review_from: RoleName = RoleName.ADVERSARY
    mutating_role: RoleName | None = None


class SecurityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network_default: Literal["deny", "allowlist"] = "deny"
    allow_unsandboxed_commands: bool = False
    fail_if_sandbox_unavailable: bool = True
    secrets: list[str] = Field(default_factory=list)


class ValueContract(BaseModel):
    """Predeclared commercial-materiality contract for one bounded task.

    The contract prevents post-hoc metric selection. Foundational tasks must name the
    customer outcome they unlock; measured tasks must declare a threshold before code is
    written; external tasks cannot be marked commercially proven by an LLM.
    """

    model_config = ConfigDict(extra="forbid")

    required: bool = True
    mode: ValueGateMode = ValueGateMode.FOUNDATIONAL
    target_user: str = "AI platform or inference engineer"
    job_to_be_done: str = "Safely qualify and upgrade an agent infrastructure stack."
    pain: str = "Cross-layer semantic regressions are difficult to detect and reproduce."
    customer_outcome: str = "A faster, safer, independently inspectable release decision."
    causal_mechanism: str = "This task enables a required part of the verified upgrade workflow."
    primary_metric: str = "foundational capability present"
    metric_direction: MetricDirection = MetricDirection.BINARY
    minimum_material_improvement: float | None = None
    measurement_unit: str | None = None
    baseline_value: float | None = None
    evidence_path: str | None = None
    parent_milestone: str | None = None
    threshold_rationale: str = "Required dependency for a predeclared sellable workflow."
    required_conditions: list[str] = Field(default_factory=list)
    falsification_criteria: list[str] = Field(default_factory=list)
    revenue_linkage: str = "Supports the paid stack-qualification and release-gate offering."
    prohibited_proxies: list[str] = Field(
        default_factory=lambda: [
            "lines of code",
            "number of generated tests without boundary coverage",
            "model-written praise",
            "synthetic customer quotes",
            "unverified willingness-to-pay claims",
        ]
    )
    required_evidence_classes: list[ValueEvidenceClass] = Field(
        default_factory=lambda: [ValueEvidenceClass.FOUNDATIONAL]
    )

    @model_validator(mode="after")
    def validate_materiality_contract(self) -> ValueContract:
        if not self.required or self.mode == ValueGateMode.NOT_REQUIRED:
            return self
        if self.mode == ValueGateMode.MEASURED:
            if self.minimum_material_improvement is None:
                raise ValueError("measured value contracts require minimum_material_improvement")
            if self.metric_direction not in {
                MetricDirection.INCREASE,
                MetricDirection.DECREASE,
                MetricDirection.BINARY,
            }:
                raise ValueError("measured value contracts require a measurable direction")
            if not self.evidence_path:
                raise ValueError("measured value contracts require evidence_path")
        if self.mode == ValueGateMode.EXTERNAL:
            if self.metric_direction != MetricDirection.EXTERNAL:
                raise ValueError("external value contracts require metric_direction=external")
            if not self.evidence_path:
                raise ValueError("external value contracts require evidence_path")
        if self.mode == ValueGateMode.FOUNDATIONAL and not self.parent_milestone:
            raise ValueError("foundational value contracts require parent_milestone")
        return self


class ValueAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ValueStatus
    summary: str
    contract_mode: ValueGateMode
    primary_metric: str
    baseline_value: float | None = None
    observed_value: float | None = None
    material_improvement: float | None = None
    threshold: float | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    evidence_classes: list[ValueEvidenceClass] = Field(default_factory=list[ValueEvidenceClass])
    falsification_attempts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    redesign_actions: list[str] = Field(default_factory=list)
    commercially_validated: bool = False


class TaskPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    title: str
    phase: str
    goal: str
    source_of_truth: list[str]
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str]
    outputs: list[str]
    stop_conditions: list[str]
    security: SecurityPolicy = Field(default_factory=SecurityPolicy)
    gates: list[Gate] = Field(default_factory=list[Gate])
    private_gate: PrivateGate = Field(default_factory=PrivateGate)
    pipeline: list[Stage]
    risk_tier: RiskTier = RiskTier.STANDARD
    context_keys: list[str] = Field(default_factory=list)
    allow_test_changes: bool = False
    remote_ci_required: bool = False
    github_push: bool = True
    commit_type: CommitType = CommitType.FEAT
    commit_subject: str | None = None
    repair: RepairPolicy = Field(default_factory=RepairPolicy)
    value_contract: ValueContract = Field(
        default_factory=lambda: ValueContract(
            required=False,
            mode=ValueGateMode.NOT_REQUIRED,
            primary_metric="internal control",
            metric_direction=MetricDirection.BINARY,
        )
    )
    task_budget_usd: float = Field(default=60.0, gt=0)
    auto_merge: bool = False
    base_branch: str = "main"

    @field_validator("pipeline")
    @classmethod
    def pipeline_not_empty(cls, value: list[Stage]) -> list[Stage]:
        if not value:
            raise ValueError("pipeline must contain at least one stage")
        return value

    @model_validator(mode="after")
    def machine_gate_names_exist(self) -> TaskPacket:
        names = {gate.name for gate in self.gates}
        if len(names) != len(self.gates):
            raise ValueError("gate names must be unique")
        for stage in self.pipeline:
            missing = sorted(set(stage.machine_gates) - names)
            if missing:
                raise ValueError(
                    f"stage {stage.role.value} references unknown machine gates: {missing}"
                )
        return self


class RoleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_file: str
    model: str
    effort: EffortLevel = "high"
    max_turns: int = Field(default=25, ge=1, le=200)
    max_budget_usd: float = Field(default=12.0, gt=0)
    task_budget_tokens: int | None = Field(default=80_000, ge=1000)
    tools: list[str]
    disallowed_tools: list[str] = Field(default_factory=list)
    permission_mode: PermissionMode = "acceptEdits"
    read_only: bool = False
    advisor_model: str | None = None
    peer_messaging: bool = False
    session_name_template: str = "tc-{task_id}-{role}-{attempt}"
    goal_condition: str | None = None


class FactoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 2
    auth_mode: Literal["max_oauth_only", "unrestricted"] = "max_oauth_only"
    allow_paid_usage: Literal[False] = False
    repo_root: str = "."
    task_dir: str = "tasks"
    artifact_dir: str = "factory/artifacts"
    worktree_dir: str = "factory/worktrees"
    ledger_path: str = "factory/state/ledger.json"
    queue_dir: str = "factory/queue"
    pipeline_state_dir: str = "factory/state/pipelines"
    feature_ledger_path: str = "factory/feature_ledger.yaml"
    autonomy_config_path: str = "config/autonomy.yaml"
    autonomy_state_path: str = "factory/state/autonomy.json"
    worker_poll_seconds: int = Field(default=30, ge=1, le=3600)
    roles_path: str = "config/roles.yaml"
    global_prompt: str = "prompts/global.md"
    monthly_budget_usd: float = Field(default=500.0, gt=0)
    require_clean_main: bool = True
    sandbox_enabled: bool = True
    project_settings_only: bool = True
    strict_mcp: bool = True
    max_parallel: int = Field(default=1, ge=1, le=8)
    private_gate_runner_env: str = "TCF_PRIVATE_GATE_RUNNER"
    completion_dir: str = "factory/completion"
    definition_of_done_path: str = "factory/product_definition_of_done.yaml"
    task_catalog_path: str = "factory/task_catalog.yaml"
    risk_profiles_path: str = "config/risk_profiles.yaml"
    context_config_path: str = "config/context.yaml"
    context_index_path: str = "docs/CONTEXT_INDEX.yaml"
    github_config_path: str = "config/github.yaml"
    claude_features_path: str = "config/claude_features.yaml"
    value_policy_path: str = "config/value_policy.yaml"
    peer_message_dir: str = "factory/messages"
    heartbeat_path: str = "factory/state/heartbeat.json"
    event_log_path: str = "factory/logs/events.jsonl"
    github_state_path: str = "factory/state/github-sync.json"
    provenance_path: str = "factory/state/provenance.jsonl"
    require_long_lived_oauth_for_autopilot: bool = True
    completion_audit_enabled: bool = True
    completion_audit_model: str = "opus"
    completion_audit_max_turns: int = Field(default=24, ge=1, le=100)
    completion_audit_budget_usd: float = Field(default=8.0, gt=0)
    quota_fallback_wait_seconds: int = Field(default=3600, ge=60, le=604_800)
    transient_retry_seconds: int = Field(default=3600, ge=30, le=86_400)
    authentication_retry_seconds: int = Field(default=3600, ge=60, le=86_400)
    crash_resume_delay_seconds: int = Field(default=120, ge=0, le=86_400)
    autopilot_lock_path: str = "factory/state/autopilot.lock"
    remote_ci_poll_seconds: int = Field(default=20, ge=5, le=300)
    remote_ci_timeout_seconds: int = Field(default=1800, ge=60, le=14_400)

    def resolve(self, repo_root: Path, value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else repo_root / candidate


class AutonomyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    enabled: bool = False
    auto_plan: bool = True
    auto_enqueue: bool = True
    auto_merge: bool = True
    auto_resume_quota: bool = True
    auto_recover_interrupted: bool = True
    auto_respec_failed_tasks: bool = True
    auto_repair_factory: bool = True
    max_self_repair_attempts: int = Field(default=3, ge=0, le=5)
    allow_paid_usage: Literal[False] = False
    max_respecifications_per_task: int = Field(default=3, ge=0, le=10)
    max_consecutive_infrastructure_recoveries: int = Field(default=2, ge=0, le=10)
    idle_poll_seconds: int = Field(default=60, ge=5, le=3600)
    quota_reset_buffer_seconds: int = Field(default=0, ge=0, le=3600)
    unknown_limit_retry_seconds: int = Field(default=3600, ge=60, le=86_400)
    max_consecutive_factory_failures: int = Field(default=5, ge=1, le=100)
    completion_target: Literal["product_build", "all_automatable"] = "product_build"
    stop_file: str = "factory/state/STOP"
    pause_file: str = "factory/state/PAUSE"
    hard_stuck_path: str = "factory/state/HARD_STUCK.json"
    hard_stuck_retry_seconds: int = Field(default=3600, ge=300, le=86_400)
    calibration_marker: str = "factory/state/CALIBRATION_PASSED"
    require_calibration: bool = True
    notification_command: str | None = None
    external_blocker_sleep_seconds: int = Field(default=3600, ge=60, le=86_400)
    auto_expand_roadmap: bool = True
    completion_audits_required: int = Field(default=2, ge=2, le=3)
    max_completion_expansions: int = Field(default=5, ge=0, le=20)
    github_sync_enabled: bool = True
    push_after_verified_tasks: int = Field(default=3, ge=1, le=50)
    push_interval_seconds: int = Field(default=1800, ge=60, le=86_400)
    push_before_quota_pause: bool = True
    push_on_integration_or_trust_task: bool = True
    push_at_completion: bool = True
    value_redesign_limit: int = Field(default=2, ge=0, le=5)
    heartbeat_seconds: int = Field(default=30, ge=5, le=3600)
    peer_cohort_timeout_seconds: int = Field(default=1200, ge=60, le=7200)


class AgentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    value_assessment: ValueAssessment | None = None


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    return_code: int
    duration_seconds: float
    passed: bool
    stdout_path: str
    stderr_path: str
    timed_out: bool = False


class StageResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    run_id: str
    role: RoleName
    attempt: int
    model: str
    verdict: Verdict
    report: AgentReport | None = None
    session_id: str | None = None
    total_cost_usd: float = 0.0
    num_turns: int = 0
    duration_ms: int = 0
    usage: dict[str, Any] = Field(default_factory=dict)
    model_usage: dict[str, Any] = Field(default_factory=dict)
    terminal_reason: str | None = None
    error: str | None = None
    commit_sha: str | None = None
    base_sha: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list[GateResult])
    artifact_dir: str
    session_name: str | None = None
    advisor_model: str | None = None
    peer_messaging_enabled: bool = False
    peer_sessions: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    goal_condition: str | None = None
    workflow_name: str | None = None
    skills: list[str] = Field(default_factory=list)


class QuotaPauseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PauseKind
    detected_at: datetime
    resume_at: datetime
    message: str
    source: str


class PipelineCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    task_id: str
    run_id: str
    starting_sha: str
    candidate_sha: str
    stage_index: int = 0
    stage_attempts: dict[str, int] = Field(default_factory=dict)
    stage_failures: dict[str, int] = Field(default_factory=dict)
    quota_resumptions: dict[str, int] = Field(default_factory=dict)
    repair_cycles: int = 0
    previous_findings: list[str] | None = None
    handoff_path: str | None = None
    remote_ci: dict[str, Any] = Field(default_factory=dict)
    state: PipelineState = PipelineState.NEW
    active_role: RoleName | None = None
    active_attempt: int | None = None
    active_base_sha: str | None = None
    active_worktree: str | None = None
    pause: QuotaPauseRecord | None = None
    results: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    value_gate: dict[str, Any] = Field(default_factory=dict)
    private_gate: dict[str, Any] = Field(default_factory=dict)
    peer_cohort: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class QueuePauseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    kind: PauseKind
    resume_at: datetime
    message: str
    run_id: str | None = None


class AutonomyState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    status: Literal[
        "disarmed",
        "idle",
        "planning",
        "running",
        "paused",
        "auditing",
        "waiting_auth",
        "repairing",
        "restarting",
        "hard_stuck",
        "complete",
        "blocked",
        "stopped",
    ] = "idle"
    active_task_id: str | None = None
    current_action: str | None = None
    consecutive_failures: int = 0
    repair_attempts: int = 0
    repair_status: str | None = None
    blocker_reason: str | None = None
    required_action: str | None = None
    last_repair_artifact: str | None = None
    completed_tasks: list[str] = Field(default_factory=list)
    blocked_tasks: list[str] = Field(default_factory=list)
    last_event: str | None = None
    next_wake_at: datetime | None = None
    updated_at: datetime


class CompletionVerdict(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"


class CompletionWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    outcome: str
    phase: str
    lead_role: str
    depends_on: list[str] = Field(default_factory=list)
    trust_core: bool = False
    evidence_required: list[str] = Field(default_factory=list)


class CompletionAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: CompletionVerdict
    summary: str
    completed_evidence: list[str] = Field(default_factory=list)
    missing_items: list[CompletionWorkItem] = Field(default_factory=list[CompletionWorkItem])
    blockers: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


AGENT_REPORT_JSON_SCHEMA: dict[str, Any] = AgentReport.model_json_schema()
VALUE_ASSESSMENT_JSON_SCHEMA: dict[str, Any] = ValueAssessment.model_json_schema()
COMPLETION_AUDIT_JSON_SCHEMA: dict[str, Any] = CompletionAuditReport.model_json_schema()
