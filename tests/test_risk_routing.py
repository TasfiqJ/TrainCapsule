from __future__ import annotations

from pathlib import Path

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
from tcfactory.risk import apply_risk_profile, effective_risk, load_risk_profiles, planning_pipeline

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
        RoleName.RELEASE,
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
    assert models[RoleName.AUDIT] == "sonnet"
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
    assert all(stage.model == "haiku" for stage in stages)


def test_integration_keeps_independent_specification_before_builder() -> None:
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
    assert [stage.role for stage in routed.pipeline[:2]] == [
        RoleName.SPECIFICATION,
        RoleName.BUILDER,
    ]
    assert routed.pipeline[0].model == "opus"
    assert routed.pipeline[1].model == "sonnet"
    assert routed.repair.mutating_role == RoleName.BUILDER
