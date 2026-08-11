from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    MetricDirection,
    ValueContract,
    ValueEvidenceClass,
    ValueGateMode,
)
from .yamlutil import load_yaml

_ADDITIVE_POLICY_LIST_FIELDS = frozenset(
    {"required_conditions", "falsification_criteria", "prohibited_proxies"}
)


class ValuePolicyError(RuntimeError):
    pass


class ValuePolicyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ValueGateMode
    target_user: str | None = None
    job_to_be_done: str | None = None
    pain: str | None = None
    customer_outcome: str | None = None
    causal_mechanism: str | None = None
    primary_metric: str | None = None
    metric_direction: MetricDirection | None = None
    minimum_material_improvement: float | None = None
    measurement_unit: str | None = None
    baseline_value: float | None = None
    evidence_path: str | None = None
    parent_milestone: str | None = None
    threshold_rationale: str | None = None
    required_conditions: list[str] = Field(default_factory=list)
    falsification_criteria: list[str] = Field(default_factory=list)
    revenue_linkage: str | None = None
    prohibited_proxies: list[str] = Field(default_factory=list)
    required_evidence_classes: list[ValueEvidenceClass] = Field(
        default_factory=list[ValueEvidenceClass]
    )


class ValuePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    defaults: dict[str, Any]
    tasks: dict[str, ValuePolicyEntry]


def load_value_policy(path: Path) -> ValuePolicy:
    if not path.is_file():
        raise ValuePolicyError(f"Value policy is missing: {path}")
    return ValuePolicy.model_validate(load_yaml(path))


def contract_for_task(policy: ValuePolicy, task_id: str) -> ValueContract:
    try:
        entry = policy.tasks[task_id]
    except KeyError as exc:
        raise ValuePolicyError(
            f"No predeclared value contract exists for {task_id}; refusing post-hoc metrics."
        ) from exc

    merged = dict(policy.defaults)
    values = entry.model_dump(exclude_none=True, mode="json")
    for key, value in values.items():
        # Empty lists mean "use defaults" unless the task intentionally supplies values.
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, list) and key in _ADDITIVE_POLICY_LIST_FIELDS:
            inherited = merged.get(key, [])
            if not isinstance(inherited, list):
                raise ValuePolicyError(f"Value policy default {key!r} must be a list")
            inherited_strings = cast(list[str], inherited)
            value_strings = cast(list[str], value)
            merged[key] = list(dict.fromkeys([*inherited_strings, *value_strings]))
            continue
        merged[key] = value
    merged["required"] = entry.mode != ValueGateMode.NOT_REQUIRED
    if entry.mode == ValueGateMode.FOUNDATIONAL and not merged.get("evidence_path"):
        merged["evidence_path"] = f"docs/evidence/{task_id}/capability-value.json"
    if entry.mode == ValueGateMode.MEASURED:
        if merged.get("primary_metric") == "all_predeclared_task_conditions_pass":
            raise ValuePolicyError(
                f"Measured task {task_id} uses a tautological completion metric"
            )
        required_conditions = [
            str(value) for value in cast(list[object], merged.get("required_conditions", []))
        ]
        required_conditions.append(f"{task_id.lower()}_primary_outcome_observed")
        merged["required_conditions"] = list(dict.fromkeys(required_conditions))
        falsifications = [
            str(value) for value in cast(list[object], merged.get("falsification_criteria", []))
        ]
        falsifications.append(
            f"{task_id} primary user outcome does not meet the predeclared metric"
        )
        merged["falsification_criteria"] = list(dict.fromkeys(falsifications))
    return ValueContract.model_validate(merged)
