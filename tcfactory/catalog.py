from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .feature_ledger import FeatureItem
from .models import (
    Gate,
    PrivateGate,
    RepairPolicy,
    RiskTier,
    RoleName,
    SecurityPolicy,
    Stage,
    TaskPacket,
    ValueGateMode,
)
from .risk import apply_risk_profile, effective_risk
from .value_policy import contract_for_task, load_value_policy
from .yamlutil import load_yaml


class CatalogEntry(BaseModel):
    """Controller-owned task definition.

    The catalog carries scope and acceptance criteria so the factory does not spend a
    frontier-model session rediscovering work that the master plan already specifies.
    A model planner is reserved for missing/ambiguous entries and later re-specification.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    phase: str
    depends_on: list[str] = Field(default_factory=list)
    risk_tier: str | None = None  # informational; the feature ledger is authoritative
    task_kind: str = "implementation"
    lead_role: str
    commit_message: str
    milestone: str | None = None
    source_sections: list[str] = Field(default_factory=list)
    allowed_paths: list[str]
    expected_outputs: list[str]
    acceptance_criteria: list[str]
    non_goals: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    network_default: str = "deny"
    allowed_domains: list[str] = Field(default_factory=list)
    gate_profiles: list[str] = Field(default_factory=list)
    private_gate_suite: str | None = None
    ui_change: bool = False
    security_sensitive: bool = False
    full_regression: bool = False
    github_push: bool = True
    require_remote_ci: bool = False


class TaskCatalog(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    source_of_truth: str
    defaults: dict[str, Any]
    tasks: dict[str, CatalogEntry]


class CatalogError(RuntimeError):
    pass


def load_task_catalog(path: Path) -> TaskCatalog:
    if not path.is_file():
        raise CatalogError(f"Task catalog is missing: {path}")
    value = load_yaml(path)
    return TaskCatalog.model_validate(value)


def has_catalog_entry(catalog: TaskCatalog, task_id: str) -> bool:
    return task_id in catalog.tasks


def _gate(task_id: str, name: str) -> Gate:
    commands = {
        "contract": f"bash scripts/gates/contract_gate.sh {task_id}",
        "secret-scan": "bash scripts/gates/secret_scan.sh",
        "fast-quality": "bash scripts/gates/fast_quality.sh",
        "full-quality": "bash scripts/gates/full_quality.sh",
        "real-integration": f"bash scripts/gates/real_integration.sh {task_id}",
        "ui-e2e": "bash scripts/gates/ui_e2e.sh",
        "milestone": f"bash scripts/gates/milestone_gate.sh {task_id}",
    }
    timeouts = {
        "contract": 120,
        "secret-scan": 300,
        "fast-quality": 1800,
        "full-quality": 3600,
        "real-integration": 3600,
        "ui-e2e": 3600,
        "milestone": 7200,
    }
    if name not in commands:
        raise CatalogError(f"Unknown gate profile {name!r} for {task_id}")
    return Gate(name=name, command=commands[name], timeout_seconds=timeouts[name])


def _initial_pipeline(
    *,
    task_id: str,
    entry: CatalogEntry,
    risk: RiskTier,
    allowed_paths: list[str],
    forbidden_paths: list[str],
    gate_names: list[str],
) -> list[Stage]:
    """Build only the writable stages; deterministic risk routing adds reviewers.

    Research-only work does not invent a coding stage. Integration and trust work get an
    independent frozen specification before implementation, while ordinary/mechanical work
    avoids that extra model session unless the catalog explicitly needs it.
    """

    spec_path = f"specs/tasks/{task_id}.md"
    stages: list[Stage] = []
    kind = entry.task_kind.lower()
    research_only = kind == "research"

    needs_independent_spec = (
        risk == RiskTier.TRUST_CORE
        or (risk == RiskTier.INTEGRATION and not research_only)
        or entry.security_sensitive
    )
    if needs_independent_spec:
        stages.append(
            Stage(
                role=RoleName.SPECIFICATION,
                allowed_paths=[spec_path],
                forbidden_paths=sorted(set(forbidden_paths + allowed_paths)),
                acceptance_criteria=[
                    "Freeze the task contract without implementing product code.",
                    "Distinguish normative, inferred, optional, and UNKNOWN behavior.",
                    "Define exact tests, failure states, protected expectations, and stop rules.",
                ],
                machine_gates=["contract"] if "contract" in gate_names else [],
                context_keys=[],
                read_only=False,
                require_changes=True,
            )
        )

    if research_only:
        stages.append(
            Stage(
                role=RoleName.RESEARCH,
                allowed_paths=allowed_paths,
                forbidden_paths=sorted(set(forbidden_paths + [spec_path])),
                allowed_domains=entry.allowed_domains,
                acceptance_criteria=entry.acceptance_criteria,
                machine_gates=gate_names,
                read_only=False,
                require_changes=True,
            )
        )
    else:
        stages.append(
            Stage(
                role=RoleName.BUILDER,
                allowed_paths=allowed_paths,
                forbidden_paths=sorted(set(forbidden_paths + [spec_path])),
                allowed_domains=entry.allowed_domains,
                acceptance_criteria=entry.acceptance_criteria,
                machine_gates=gate_names,
                read_only=False,
                require_changes=True,
            )
        )
    return stages


def task_packet_from_catalog(
    *,
    repo_root: Path,
    item: FeatureItem,
    catalog: TaskCatalog,
    risk_profiles: dict[str, Any],
) -> TaskPacket:
    try:
        entry = catalog.tasks[item.task_id]
    except KeyError as exc:
        raise CatalogError(f"No task catalog entry for {item.task_id}") from exc

    if entry.depends_on != item.depends_on:
        raise CatalogError(
            f"Catalog dependencies for {item.task_id} do not match the feature ledger: "
            f"{entry.depends_on!r} != {item.depends_on!r}"
        )

    defaults = catalog.defaults
    source_files = [str(value) for value in defaults.get("source_of_truth", [])]
    source_files.append(catalog.source_of_truth)
    source_files = list(dict.fromkeys(source_files))
    forbidden = [str(value) for value in defaults.get("forbidden_paths", [])]
    gate_names = list(dict.fromkeys(entry.gate_profiles))
    gates = [_gate(item.task_id, name) for name in gate_names]
    risk = effective_risk(item)
    research_only = entry.task_kind.lower() == "research"
    allowed_paths = list(dict.fromkeys(entry.allowed_paths))
    spec_path = f"specs/tasks/{item.task_id}.md"
    outputs = list(dict.fromkeys(entry.expected_outputs))
    value_policy = load_value_policy(repo_root / "config/value_policy.yaml")
    value_contract = contract_for_task(value_policy, item.task_id)
    if value_contract.mode == ValueGateMode.MEASURED and value_contract.evidence_path:
        allowed_paths = list(dict.fromkeys([*allowed_paths, value_contract.evidence_path]))
        outputs = list(dict.fromkeys([*outputs, value_contract.evidence_path]))

    initial = _initial_pipeline(
        task_id=item.task_id,
        entry=entry,
        risk=risk,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden,
        gate_names=gate_names,
    )
    if any(stage.role == RoleName.SPECIFICATION for stage in initial):
        outputs = [spec_path, *outputs]

    private_required = risk in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}
    suite = entry.private_gate_suite
    if private_required and not suite:
        suite = "trust-core-mutations" if risk == RiskTier.TRUST_CORE else "integration-paths"

    profile = risk_profiles["profiles"][risk.value]
    task_budget = float(profile["task_budget_usd"])
    repair_models = ["sonnet"]
    if risk in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}:
        repair_models.append("opus")

    packet = TaskPacket(
        task_id=item.task_id,
        title=entry.title,
        phase=entry.phase,
        goal=f"Complete the bounded roadmap outcome: {entry.title}.",
        source_of_truth=source_files,
        depends_on=entry.depends_on,
        inputs=[
            f"Roadmap item: {item.task_id}",
            f"Lead role: {entry.lead_role}",
            f"Risk tier: {risk.value}",
            *[f"Master-plan section: {section}" for section in entry.source_sections],
        ],
        non_goals=entry.non_goals,
        acceptance_criteria=[
            *entry.acceptance_criteria,
            (
                "Produce the predeclared material-value evidence and satisfy every required "
                "condition; "
                "a technically working but immaterial result must return to redesign."
                if value_contract.mode == ValueGateMode.MEASURED
                else (
                    "Preserve the task's explicit causal link to its predeclared sellable "
                    "milestone without inventing demand."
                )
            ),
            "Never lower a value threshold after observing the result unless a separately "
            "reviewed ADR cites new external evidence.",
        ],
        outputs=outputs,
        stop_conditions=entry.stop_conditions,
        security=SecurityPolicy(
            network_default=("allowlist" if entry.network_default == "allowlist" else "deny"),
            allow_unsandboxed_commands=False,
            fail_if_sandbox_unavailable=True,
            secrets=[],
        ),
        gates=gates,
        private_gate=PrivateGate(
            required=private_required,
            suite=suite if private_required else None,
            timeout_seconds=3600 if private_required else 1800,
        ),
        pipeline=initial,
        risk_tier=risk,
        context_keys=item.context_keys,
        allow_test_changes=item.allow_test_changes,
        remote_ci_required=(
            entry.require_remote_ci
            or item.remote_ci_required
            or risk in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}
        ),
        github_push=entry.github_push,
        commit_type=item.commit_type,
        commit_subject=entry.commit_message,
        value_contract=value_contract,
        repair=RepairPolicy(
            enabled=True,
            max_cycles=2 if risk in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE} else 1,
            builder_models=repair_models,
            restart_review_from=(
                RoleName.ADVERSARY
                if risk in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}
                else RoleName.RELEASE
            ),
            mutating_role=RoleName.RESEARCH if research_only else RoleName.BUILDER,
        ),
        task_budget_usd=task_budget,
        auto_merge=True,
        base_branch="main",
    )
    routed = apply_risk_profile(packet, item, risk_profiles)
    # Keep controller-owned fields from the ledger/catalog after routing.
    return routed.model_copy(
        update={
            "commit_subject": entry.commit_message,
            "remote_ci_required": packet.remote_ci_required,
            "github_push": packet.github_push,
            "allow_test_changes": packet.allow_test_changes,
            "outputs": outputs,
        }
    )


def write_task_packet(path: Path, packet: TaskPacket) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(packet.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
