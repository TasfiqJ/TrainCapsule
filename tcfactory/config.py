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


def load_factory_config(path: Path) -> FactoryConfig:
    config = FactoryConfig.model_validate(_load_yaml(path))
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
    config = AutonomyConfig.model_validate(_load_yaml(path))
    overrides: dict[str, object] = {}
    enabled = os.getenv("TCF_AUTONOMY_ENABLED")
    if enabled is not None:
        overrides["enabled"] = enabled.strip().lower() in {"1", "true", "yes", "on"}
    auto_merge = os.getenv("TCF_AUTO_MERGE")
    if auto_merge is not None:
        overrides["auto_merge"] = auto_merge.strip().lower() in {"1", "true", "yes", "on"}
    return config.model_copy(update=overrides) if overrides else config


def load_task(path: Path) -> TaskPacket:
    return TaskPacket.model_validate(_load_yaml(path))


def load_roles(path: Path) -> dict[RoleName, RoleConfig]:
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        raise ValueError("roles.yaml must be a mapping")
    typed_raw = cast(dict[object, object], raw)
    return {
        RoleName(str(name)): RoleConfig.model_validate(value) for name, value in typed_raw.items()
    }
