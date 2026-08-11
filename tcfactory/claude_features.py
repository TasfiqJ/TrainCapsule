from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import RiskTier, RoleConfig, RoleName, Stage, TaskPacket
from .yamlutil import load_yaml


class ClaudeFeatureError(RuntimeError):
    pass


class CrossSessionMessagingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    minimum_cli_version: str = "2.1.224"
    risk_tiers: list[RiskTier] = Field(default_factory=lambda: [RiskTier.TRUST_CORE])
    roles: list[RoleName] = Field(
        default_factory=lambda: [RoleName.BUILDER, RoleName.INTEGRATION_SCOUT]
    )
    max_messages_per_session: int = Field(default=4, ge=1, le=20)
    max_message_chars: int = Field(default=1200, ge=128, le=5000)
    same_machine_only: bool = True
    isolate_peer_machines: bool = True
    require_durable_handoff: bool = True


class AdvisorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model: str = "opus"
    risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    roles: list[RoleName] = Field(default_factory=lambda: [RoleName.BUILDER, RoleName.RECOVERY])


class ScoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    risk_tiers: list[RiskTier] = Field(default_factory=lambda: [RiskTier.TRUST_CORE])
    role: RoleName = RoleName.INTEGRATION_SCOUT
    timeout_seconds: int = Field(default=900, ge=60, le=3600)
    startup_delay_seconds: float = Field(default=0.75, ge=0, le=10)
    blocking_on_concrete_failure: bool = True
    blocking_on_non_pass: bool = True


class GoalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    minimum_cli_version: str = "2.1.224"
    risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    roles: list[RoleName] = Field(default_factory=lambda: [RoleName.BUILDER])
    max_condition_chars: int = Field(default=1800, ge=128, le=4000)
    max_turn_clause: int = Field(default=20, ge=2, le=100)
    note: str = (
        "Goal mode keeps a bounded builder working, but deterministic controller gates remain "
        "the only release authority because the goal evaluator reads the transcript rather than "
        "independently executing the environment."
    )


class DynamicWorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    minimum_cli_version: str = "2.1.202"
    size_guideline: str = "small"
    roles: list[RoleName] = Field(default_factory=lambda: [RoleName.RESEARCH])
    risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    task_allowlist: list[str] = Field(default_factory=lambda: ["T001", "T002", "T003"])
    max_agents_guideline: int = Field(default=4, ge=1, le=8)
    non_authoritative: bool = True
    reason: str = (
        "Programmatic Workflow tool use remains disabled until the Python Agent SDK "
        "explicitly documents support. Saved workflow files may be used manually after "
        "operator verification."
    )


class AgentTeamsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    reason: str = (
        "Agent teams multiply context and token usage. The default factory uses controller-owned "
        "fresh sessions and one tiny peer scout only where collaboration has concrete value."
    )


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_memory_enabled: bool = False
    durable_handoffs_only: bool = True


class ClaudeFeaturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 2
    cross_session_messaging: CrossSessionMessagingConfig = Field(
        default_factory=CrossSessionMessagingConfig
    )
    advisor: AdvisorConfig = Field(default_factory=AdvisorConfig)
    integration_scout: ScoutConfig = Field(default_factory=ScoutConfig)
    goal: GoalConfig = Field(default_factory=GoalConfig)
    dynamic_workflows: DynamicWorkflowConfig = Field(default_factory=DynamicWorkflowConfig)
    agent_teams: AgentTeamsConfig = Field(default_factory=AgentTeamsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    role_skills: dict[str, list[str]] = Field(default_factory=dict)


@dataclass(frozen=True)
class SessionFeaturePlan:
    session_name: str
    advisor_model: str | None
    peer_messaging: bool
    peer_names: tuple[str, ...]
    goal_condition: str | None
    workflow_name: str | None
    tools: tuple[str, ...]
    skills: tuple[str, ...]
    settings_payload: dict[str, Any]


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION_RE.search(value)
    if not match:
        raise ClaudeFeatureError(f"Cannot parse Claude Code version from {value!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def installed_claude_version() -> str | None:
    try:
        result = subprocess.run(
            ["claude", "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip() or None


def assert_minimum_version(current: str, required: str, feature: str) -> None:
    if version_tuple(current) < version_tuple(required):
        raise ClaudeFeatureError(f"{feature} requires Claude Code >= {required}; found {current}")


def load_claude_features(path: Path) -> ClaudeFeaturesConfig:
    if not path.is_file():
        raise ClaudeFeatureError(f"Claude feature configuration is missing: {path}")
    return ClaudeFeaturesConfig.model_validate(load_yaml(path))


def make_session_name(task_id: str, role: RoleName, run_id: str, attempt: int) -> str:
    safe_task = re.sub(r"[^a-z0-9-]+", "-", task_id.lower()).strip("-")
    safe_role = re.sub(r"[^a-z0-9-]+", "-", role.value.lower()).strip("-")
    suffix = re.sub(r"[^a-z0-9]+", "", run_id.lower())[-8:]
    return f"rp-{safe_task}-{safe_role}-{suffix}-a{attempt}"[:80]


def should_launch_scout(features: ClaudeFeaturesConfig, task: TaskPacket, stage: Stage) -> bool:
    config = features.integration_scout
    return config.enabled and stage.role == RoleName.BUILDER and task.risk_tier in config.risk_tiers


def _default_goal(task: TaskPacket, max_turns: int) -> str:
    required_gates = (
        ", ".join(gate.name for gate in task.gates if gate.required) or "all required gates"
    )
    return (
        f"Complete only task {task.task_id}; every acceptance criterion is evidenced; "
        f"{required_gates} exit successfully; no forbidden or protected path changes; "
        "no test, oracle, value threshold, "
        "or expected result is weakened; and git diff contains only allowed task work. "
        f"Stop and return BLOCKED instead of guessing, or stop after {max_turns} evaluated turns."
    )


def _workflow_for_task(
    features: ClaudeFeaturesConfig, task: TaskPacket, stage: Stage
) -> str | None:
    config = features.dynamic_workflows
    if stage.workflow_name:
        return stage.workflow_name
    if (
        config.enabled
        and stage.role in config.roles
        and task.risk_tier in config.risk_tiers
        and (not config.task_allowlist or task.task_id in config.task_allowlist)
    ):
        return "source-crosscheck"
    return None


def build_session_feature_plan(
    *,
    features: ClaudeFeaturesConfig,
    task: TaskPacket,
    stage: Stage,
    role_config: RoleConfig,
    run_id: str,
    attempt: int,
    peer_names: list[str] | None = None,
    session_name_override: str | None = None,
    peer_messaging_override: bool | None = None,
) -> SessionFeaturePlan:
    session_name = (
        session_name_override
        or stage.session_name
        or make_session_name(task.task_id, stage.role, run_id, attempt)
    )
    peers = tuple(peer_names or [])
    messaging_cfg = features.cross_session_messaging
    messaging = (
        messaging_cfg.enabled
        and task.risk_tier in messaging_cfg.risk_tiers
        and stage.role in messaging_cfg.roles
        and bool(peers)
    )
    if peer_messaging_override is not None:
        messaging = peer_messaging_override and messaging_cfg.enabled and bool(peers)
    if stage.peer_messaging or role_config.peer_messaging:
        messaging = messaging_cfg.enabled and bool(peers)

    advisor_cfg = features.advisor
    advisor = stage.advisor_model or role_config.advisor_model
    main_model = stage.model or role_config.model
    if (
        advisor is None
        and advisor_cfg.enabled
        and main_model == "sonnet"
        and task.risk_tier in advisor_cfg.risk_tiers
        and stage.role in advisor_cfg.roles
    ):
        advisor = advisor_cfg.model

    goal_condition = stage.goal_condition or role_config.goal_condition
    goal_cfg = features.goal
    if (
        goal_condition is None
        and goal_cfg.enabled
        and stage.role in goal_cfg.roles
        and task.risk_tier in goal_cfg.risk_tiers
    ):
        goal_condition = _default_goal(
            task, min(stage.max_turns or role_config.max_turns, goal_cfg.max_turn_clause)
        )
    if goal_condition and len(goal_condition) > goal_cfg.max_condition_chars:
        goal_condition = goal_condition[: goal_cfg.max_condition_chars - 3] + "..."

    workflow_name = _workflow_for_task(features, task, stage)
    tools: list[str] = []
    if messaging:
        tools.extend(["ListAgents", "SendMessage"])
    if workflow_name:
        tools.append("Workflow")

    skills = tuple(features.role_skills.get(stage.role.value, []))
    settings_payload: dict[str, Any] = {
        "autoMemoryEnabled": features.memory.auto_memory_enabled,
        "crossSessionInbound": "accept" if messaging else "refuse",
        "isolatePeerMachines": messaging_cfg.isolate_peer_machines,
        "workflowSizeGuideline": features.dynamic_workflows.size_guideline,
        "disableRemoteControl": True,
        "attribution": {"commit": "", "pr": "", "sessionUrl": False},
    }
    return SessionFeaturePlan(
        session_name=session_name,
        advisor_model=advisor,
        peer_messaging=messaging,
        peer_names=peers,
        goal_condition=goal_condition,
        workflow_name=workflow_name,
        tools=tuple(tools),
        skills=skills,
        settings_payload=settings_payload,
    )


def write_flag_settings(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
