from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from scripts.generate_v3_roadmap import build_collection, rendered
from scripts.generate_v3_schemas import SCHEMAS
from tcfactory.cli import app
from tcfactory.config import load_autonomy_config, load_factory_config
from tcfactory.models import AutonomyConfig
from tcfactory.v3.configuration import (
    AutonomyV3Config,
    CommercialMaturityConfig,
    ExecutorConfig,
    ExternalEvidenceConfig,
    FactoryV3Config,
    MilestonePolicyConfig,
    load_autonomy_v3,
    load_executors_v3,
    load_factory_v3,
    load_scheduler_v3,
)
from tcfactory.v3.enums import MilestoneStatus, WorkKind, WorkStatus
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_v3_configuration_is_finite_and_fail_closed() -> None:
    factory = load_factory_v3(ROOT / "config/factory.yaml")
    autonomy = load_autonomy_v3(ROOT / "config/autonomy.yaml")
    scheduler = load_scheduler_v3(ROOT / "config/scheduler.yaml")
    executors = load_executors_v3(ROOT / "config/executors.yaml")
    external = ExternalEvidenceConfig.model_validate(
        load_yaml(ROOT / "config/external_evidence.yaml")
    )
    commercial = CommercialMaturityConfig.model_validate(
        load_yaml(ROOT / "config/commercial_maturity.yaml")
    )
    milestones = MilestonePolicyConfig.model_validate(
        load_yaml(ROOT / "config/milestones.yaml")
    )

    assert isinstance(factory, FactoryV3Config)
    assert isinstance(autonomy, AutonomyV3Config)
    assert isinstance(executors, ExecutorConfig)
    assert factory.allow_paid_usage is False
    assert factory.schema_version == "3.1"
    assert factory.repository.direct_main_push is False
    assert (
        factory.repository.release_mode
        == "AUTOMATED_PR_REQUIRED_CHECKS_MACHINE_RECEIPT_AUTO_MERGE"
    )
    assert factory.release.publisher_capability == "PENDING_PHASE_4"
    assert factory.execution.work_until_done is False
    assert all(
        value > 0
        for value in (
            autonomy.planning.max_plan_attempts,
            autonomy.candidate.max_candidate_repair_cycles,
            autonomy.candidate.max_same_finding_repeats,
            autonomy.candidate.max_candidate_restarts,
            autonomy.recovery.max_infrastructure_recoveries_per_run,
            autonomy.recovery.max_factory_self_repairs_per_incident,
            autonomy.recovery.max_controller_restarts,
            autonomy.value.max_value_redesigns,
            autonomy.completion.max_expansion_rounds_per_milestone,
            autonomy.completion.max_expansion_items,
        )
    )
    assert autonomy.enabled is False
    assert autonomy.external.ai_may_complete_external_evidence is False
    assert autonomy.completion.roadmap_expansion_requires_machine_policy_receipt is True
    assert autonomy.external.machine_policy_receipts_required is True
    assert "human" not in autonomy.model_dump_json(by_alias=True).lower()
    assert external.allow_repository_fallback is False
    assert external.agent_writable is False
    assert commercial.synthetic_evidence_may_advance is False
    assert commercial.repository_authored_receipts_are_trusted is False
    assert milestones.source_migration_machine_policy_receipt_required is True
    assert scheduler.active_milestone == milestones.active_milestone
    assert executors.allow_paid_usage is False


def test_v3_factory_payload_is_not_silently_accepted_as_v31(tmp_path: Path) -> None:
    legacy = tmp_path / "factory.yaml"
    legacy.write_text("version: 3\nallowPaidUsage: false\n", encoding="utf-8")
    with pytest.raises(ValueError, match="migration input only"):
        load_factory_config(legacy)


def test_legacy_loader_projects_v3_configuration_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = load_factory_config(ROOT / "config/factory.yaml")
    autonomy = load_autonomy_config(ROOT / "config/autonomy.yaml")
    assert factory.version == 3
    assert factory.work_until_done is False
    assert autonomy.version == 3
    assert autonomy.enabled is False
    assert autonomy.auto_merge is False
    assert autonomy.auto_expand_roadmap is False
    monkeypatch.setenv("TCF_AUTO_MERGE", "true")
    with pytest.raises(ValueError, match="forbids enabling automatic merge"):
        load_autonomy_config(ROOT / "config/autonomy.yaml")


def test_zero_no_longer_means_unlimited_in_compatibility_model() -> None:
    for field in (
        "max_respecifications_per_task",
        "max_completion_expansions",
        "value_redesign_limit",
    ):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            AutonomyConfig.model_validate({field: 0})


def test_authoritative_roadmap_generation_is_exact_and_typed() -> None:
    checked_in = (ROOT / "factory/roadmap/work_items.yaml").read_text(encoding="utf-8")
    assert rendered() == checked_in
    collection = WorkItemCollection.model_validate(
        load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    )
    generated = build_collection()
    assert collection == generated
    assert len(collection.work_items) == 109
    assert collection.active_milestone == "M0_FACTORY_MIGRATED"
    assert collection.item("V3-MIG-016").status is WorkStatus.BLOCKED_POLICY
    assert collection.item("V3-MIG-019").status is WorkStatus.PROPOSED
    assert all(item.source_dependency_expression is not None for item in collection.work_items)
    assert sum(item.status is WorkStatus.WAITING_EXTERNAL for item in collection.work_items) == 12
    for identifier in ("V3-MKT-005", "V3-MKT-006", "V3-MKT-007"):
        item = collection.item(identifier)
        assert item.kind is WorkKind.EXTERNAL_EVIDENCE
        assert item.status is WorkStatus.WAITING_EXTERNAL
        assert item.external_receipt_required is True
        assert item.automatable is False
    assert "WAITING_HUMAN" not in WorkStatus.__members__
    assert "WAITING_HUMAN" not in MilestoneStatus.__members__
    assert sum(item.kind is WorkKind.MACHINE_POLICY_REVIEW for item in collection.work_items) == 11
    for item in collection.work_items:
        if item.kind is WorkKind.MACHINE_POLICY_REVIEW:
            assert item.owner_type.value == "MACHINE_POLICY_AUTHORITY"
            assert item.automatable is False
            assert item.machine_policy_receipt_required is True
            assert item.retry_policy.max_plan_attempts == 0
            assert item.retry_policy.max_candidate_repair_cycles == 0
    decision = collection.item("V3-DEC-001")
    assert decision.owner_type.value == "MACHINE_POLICY_AUTHORITY"
    assert decision.automatable is False
    assert "human" not in collection.model_dump_json(by_alias=True).lower()


def test_m0_through_m6_are_bounded_and_external_milestones_remain_waiting() -> None:
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    assert len(roadmap.milestones) == 7
    assert roadmap.milestones[0].status is MilestoneStatus.ACTIVE
    assert roadmap.milestones[1].status is MilestoneStatus.PROPOSED
    external = roadmap.milestones[3:]
    assert all(item.status is MilestoneStatus.WAITING_EXTERNAL for item in external)
    assert all(item.required_evidence for item in roadmap.milestones)
    assert all(item.forbidden_claims for item in roadmap.milestones)
    assert "human" not in roadmap.model_dump_json(by_alias=True).lower()


def test_every_generated_schema_rejects_unknown_top_level_fields() -> None:
    assert len(SCHEMAS) == 43
    assert {
        "private-gate-receipt.schema.json",
        "milestone-runtime-state.schema.json",
        "milestone-completion-receipt.schema.json",
        "milestone-advance-transaction.schema.json",
        "work-item-completion-evidence.schema.json",
    } <= set(SCHEMAS)
    for model in SCHEMAS.values():
        schema = cast(dict[str, object], model.model_json_schema(by_alias=True))
        assert schema.get("additionalProperties") is False


def test_v3_scheduler_cli_is_dry_run_only_and_does_not_mutate_roadmap() -> None:
    runner = CliRunner()
    path = ROOT / "factory/roadmap/work_items.yaml"
    before = path.read_bytes()
    refused = runner.invoke(app, ["v3-schedule", "--repo", str(ROOT)])
    assert refused.exit_code == 2
    result = runner.invoke(
        app,
        ["v3-schedule", "--repo", str(ROOT), "--dry-run", "--explain"],
    )
    assert result.exit_code == 0, result.output
    assert '"activeMilestone": "M0_FACTORY_MIGRATED"' in result.output
    assert '"selectedWorkItemIds"' in result.output
    assert path.read_bytes() == before


def test_v3_repository_refuses_legacy_mutating_cli_surfaces() -> None:
    runner = CliRunner()
    commands = (
        ["run", "tasks/T002.yaml"],
        ["enqueue", "tasks/T002.yaml"],
        ["worker"],
        ["completion-audit"],
        ["queue-reconcile"],
    )
    for command in commands:
        result = runner.invoke(app, [*command, "--repo", str(ROOT)])
        assert result.exit_code != 0
        observed = result.output or str(result.exception)
        assert "disabled" in observed.lower()
