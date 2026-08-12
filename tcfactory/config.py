from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from .models import AutonomyConfig, FactoryConfig, RoleConfig, RoleName, TaskPacket
from .yamlutil import load_yaml


def _load_yaml(path: Path) -> object:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return load_yaml(path)


def _is_v3_payload(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return cast(dict[str, object], value).get("version") == 3


def load_factory_config(path: Path) -> FactoryConfig:
    raw = _load_yaml(path)
    is_v31_factory = isinstance(raw, dict) and (
        cast(dict[str, object], raw).get("schemaVersion") == "3.1"
    )
    if is_v31_factory:
        from tcfactory.v3.configuration import FactoryV3Config

        v3 = FactoryV3Config.model_validate(raw)
        config = FactoryConfig(
            version=3,
            allow_paid_usage=False,
            require_clean_main=v3.repository.require_clean_base,
            work_until_done=False,
            max_parallel=v3.execution.max_concurrent_mutating_sessions,
            context_index_path=v3.source_of_truth.context_index,
            autonomy_config_path="config/autonomy.yaml",
        )
    elif _is_v3_payload(cast(object, raw)):
        raise ValueError(
            "V3 factory configuration is migration input only; "
            "active runtime requires exact V3.1 authority"
        )
    else:
        config = FactoryConfig.model_validate(raw)
    overrides: dict[str, object] = {}

    monthly_budget = os.getenv("TCF_MONTHLY_ESTIMATED_USD_CAP") or os.getenv(
        "TCF_MONTHLY_BUDGET_USD"
    )
    if monthly_budget:
        try:
            value = float(monthly_budget)
        except ValueError as exc:
            raise ValueError("TCF_MONTHLY_ESTIMATED_USD_CAP must be a positive number") from exc
        if value <= 0:
            raise ValueError("TCF_MONTHLY_ESTIMATED_USD_CAP must be greater than zero")
        overrides["monthly_budget_usd"] = value

    max_parallel = os.getenv("TCF_MAX_PARALLEL")
    if max_parallel:
        try:
            value = int(max_parallel)
        except ValueError as exc:
            raise ValueError("TCF_MAX_PARALLEL must be an integer") from exc
        if not 1 <= value <= 8:
            raise ValueError("TCF_MAX_PARALLEL must be between 1 and 8")
        overrides["max_parallel"] = value

    return config.model_copy(update=overrides) if overrides else config


def load_autonomy_config(path: Path) -> AutonomyConfig:
    raw = _load_yaml(path)
    is_v3 = _is_v3_payload(raw)
    if is_v3:
        from tcfactory.v3.configuration import AutonomyV3Config

        v3 = AutonomyV3Config.model_validate(raw)
        config = AutonomyConfig(
            version=3,
            enabled=v3.enabled,
            auto_plan=v3.planning.auto_plan,
            auto_enqueue=True,
            auto_merge=False,
            auto_resume_quota=v3.recovery.auto_resume_quota,
            auto_recover_interrupted=v3.recovery.auto_recover_interrupted,
            auto_respec_failed_tasks=False,
            auto_repair_factory=True,
            max_self_repair_attempts=v3.recovery.max_factory_self_repairs_per_incident,
            max_respecifications_per_task=v3.planning.max_plan_attempts,
            max_consecutive_infrastructure_recoveries=(
                v3.recovery.max_infrastructure_recoveries_per_run
            ),
            auto_expand_roadmap=False,
            max_completion_expansions=v3.completion.max_expansion_rounds_per_milestone,
            value_redesign_limit=v3.value.max_value_redesigns,
        )
    else:
        config = AutonomyConfig.model_validate(raw)
    overrides: dict[str, object] = {}
    enabled = os.getenv("TCF_AUTONOMY_ENABLED")
    if enabled is not None:
        overrides["enabled"] = enabled.strip().lower() in {"1", "true", "yes", "on"}
    auto_merge = os.getenv("TCF_AUTO_MERGE")
    if auto_merge is not None:
        requested = auto_merge.strip().lower() in {"1", "true", "yes", "on"}
        if is_v3 and requested:
            raise ValueError("V3 policy forbids enabling automatic merge")
        overrides["auto_merge"] = requested
    return config.model_copy(update=overrides) if overrides else config


def load_task(path: Path) -> TaskPacket:
    return TaskPacket.model_validate(_load_yaml(path))


def load_roles(path: Path) -> dict[RoleName, RoleConfig]:
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        raise ValueError("roles.yaml must be a mapping")
    typed_raw = cast(dict[object, object], raw)
    if typed_raw.get("version") != 3:
        raise ValueError("roles.yaml must declare version 3")
    return {
        RoleName(str(name)): RoleConfig.model_validate(value)
        for name, value in typed_raw.items()
        if name != "version"
    }
