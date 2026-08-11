from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from tcfactory.config import load_task
from tcfactory.feature_ledger import FeatureItem
from tcfactory.models import (
    Gate,
    PrivateGate,
    RiskTier,
    RoleName,
    SecurityPolicy,
    Stage,
    TaskPacket,
)
from tcfactory.pipeline import run_pipeline
from tcfactory.planner import planning_task_for
from tcfactory.risk import (
    RiskProfileError,
    apply_risk_profile,
    effective_risk,
    load_risk_profiles,
    planning_pipeline,
    with_working_token_reserve,
)
from tcfactory.stage_policy import objective_pipeline_errors

ROOT = Path(__file__).resolve().parents[1]


def _packet() -> TaskPacket:
    return TaskPacket(
        task_id="T900",
        title="Add ordinary endpoint",
        phase="test",
        goal="Add one endpoint",
        source_of_truth=["docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md"],
        acceptance_criteria=["endpoint works"],
        outputs=["apps/api/example.py", "tests/api/test_example.py"],
        stop_conditions=["authority missing"],
        security=SecurityPolicy(),
        gates=[Gate(name="tests", command="pytest", stages=[RoleName.BUILDER])],
        private_gate=PrivateGate(required=False),
        pipeline=[
            Stage(
                role=RoleName.BUILDER,
                allowed_paths=["apps/api/**", "tests/api/**"],
                forbidden_paths=["config/**"],
                machine_gates=["tests"],
            )
        ],
    )


def test_standard_pipeline_uses_sonnet_for_every_stage() -> None:
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    item = FeatureItem(
        task_id="T900",
        outcome="Add ordinary endpoint",
        lead_role="Builder",
        phase="Web",
        risk_tier=RiskTier.STANDARD,
        context_keys=["web_product"],
    )
    packet = apply_risk_profile(_packet(), item, profiles)
    assert packet.risk_tier == RiskTier.STANDARD
    assert [stage.role for stage in packet.pipeline] == [
        RoleName.BUILDER,
        RoleName.ADVERSARY,
    ]
    assert all(stage.model == "sonnet" for stage in packet.pipeline)
    assert packet.private_gate.required is False


def test_integration_pipeline_reserves_opus_for_spec_and_adversary() -> None:
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    item = FeatureItem(
        task_id="T901",
        outcome="Add GitHub integration adapter",
        lead_role="Builder",
        phase="Integration",
        risk_tier=RiskTier.INTEGRATION,
        context_keys=["release"],
    )
    packet = apply_risk_profile(_packet().model_copy(update={"task_id": "T901"}), item, profiles)
    models = {stage.role: stage.model for stage in packet.pipeline}
    assert models[RoleName.BUILDER] == "sonnet"
    assert models[RoleName.ADVERSARY] == "opus"
    assert set(models) == {RoleName.BUILDER, RoleName.ADVERSARY}
    assert packet.private_gate.required is True
    assert packet.remote_ci_required is True


def test_controller_can_raise_but_not_lower_trust_core() -> None:
    item = FeatureItem(
        task_id="T902",
        outcome="Implement independent oracle",
        lead_role="Builder",
        phase="Trust core",
        trust_core=True,
        risk_tier=RiskTier.MECHANICAL,
    )
    assert effective_risk(item) == RiskTier.TRUST_CORE


def test_mechanical_planning_omits_expensive_adversary() -> None:
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    item = FeatureItem(
        task_id="T903",
        outcome="Rename generated metadata",
        lead_role="Builder",
        phase="Maintenance",
        risk_tier=RiskTier.MECHANICAL,
    )
    stages, _, _ = planning_pipeline(item, profiles)
    assert [stage.role for stage in stages] == [RoleName.PLANNER]
    assert all(stage.model == "sonnet" for stage in stages)


def test_every_planning_risk_tier_satisfies_runtime_objective_policy() -> None:
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    for index, tier in enumerate(RiskTier):
        item = FeatureItem(
            task_id=f"T91{index}",
            outcome="Compile an exact executable task contract",
            lead_role="Planner",
            phase="Planning",
            risk_tier=tier,
        )
        packet = planning_task_for(item, profiles=profiles)
        assert objective_pipeline_errors(packet) == []


def test_every_planning_profile_has_finite_session_and_token_caps() -> None:
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    for tier in RiskTier:
        item = FeatureItem(
            task_id=f"PLAN_{tier.value.upper()}",
            outcome="Plan a bounded regression task",
            lead_role="Planner",
            phase="test",
            risk_tier=tier,
        )
        stages, _, _ = planning_pipeline(item, profiles)
        for stage in stages:
            assert stage.max_context_chars is not None
            assert stage.task_budget_tokens is not None
            assert stage.max_budget_usd is not None
            assert stage.max_turns is not None
            assert stage.max_turns <= 200


def test_t002_adversary_cannot_be_upgraded_to_work_until_done() -> None:
    task = load_task(ROOT / "tasks/T002.yaml")
    adversary = next(stage for stage in task.pipeline if stage.role == RoleName.ADVERSARY)

    assert adversary.max_context_chars == 110_000
    assert adversary.task_budget_tokens is None
    assert adversary.max_budget_usd is None
    with pytest.raises(RiskProfileError, match="work_until_done is forbidden"):
        with_working_token_reserve(
            adversary,
            work_until_done=True,
            mutating_turn_floor=200,
            review_turn_floor=80,
        )


def test_work_until_done_is_rejected_in_v3() -> None:
    task = load_task(ROOT / "tasks/T002.yaml")
    research = next(stage for stage in task.pipeline if stage.role == RoleName.RESEARCH)

    with pytest.raises(RiskProfileError, match="work_until_done is forbidden"):
        with_working_token_reserve(
            research,
            work_until_done=True,
            mutating_turn_floor=200,
            review_turn_floor=80,
        )


def test_pipeline_applies_runtime_working_token_reserve_before_stage_execution() -> None:
    source = inspect.getsource(run_pipeline)

    assert "work_until_done=config.work_until_done" in source


def test_integration_keeps_one_owner_without_broadening_path_scope() -> None:
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    packet = _packet().model_copy(
        update={
            "task_id": "T904",
            "pipeline": [
                Stage(
                    role=RoleName.SPECIFICATION,
                    allowed_paths=["specs/tasks/T904.md"],
                    forbidden_paths=["src/**"],
                    machine_gates=["tests"],
                ),
                Stage(
                    role=RoleName.BUILDER,
                    allowed_paths=["apps/api/**", "tests/api/**"],
                    forbidden_paths=["config/**"],
                    machine_gates=["tests"],
                ),
            ],
        }
    )
    item = FeatureItem(
        task_id="T904",
        outcome="Add an external runtime adapter",
        lead_role="Builder",
        phase="Integration",
        risk_tier=RiskTier.INTEGRATION,
        context_keys=["runtime_adapters"],
    )
    routed = apply_risk_profile(packet, item, profiles)
    assert [stage.role for stage in routed.pipeline] == [
        RoleName.BUILDER,
        RoleName.ADVERSARY,
    ]
    assert routed.pipeline[0].allowed_paths == ["apps/api/**", "tests/api/**"]
    assert routed.pipeline[0].require_changes is True
    assert routed.pipeline[0].model == "sonnet"
    assert routed.repair.mutating_role == RoleName.BUILDER
