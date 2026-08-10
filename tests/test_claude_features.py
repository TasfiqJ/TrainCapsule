from pathlib import Path

from tcfactory.claude_features import build_session_feature_plan, load_claude_features
from tcfactory.config import load_roles
from tcfactory.models import (
    Gate,
    PrivateGate,
    RiskTier,
    RoleName,
    SecurityPolicy,
    Stage,
    TaskPacket,
)

ROOT = Path(__file__).resolve().parents[1]


def _task(risk: RiskTier = RiskTier.TRUST_CORE) -> TaskPacket:
    return TaskPacket(
        task_id="T999",
        title="Verify a trust primitive",
        phase="test",
        goal="Implement one bounded primitive",
        source_of_truth=["docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md"],
        acceptance_criteria=["the primitive is verified"],
        outputs=["src/example.py"],
        stop_conditions=["authority missing"],
        risk_tier=risk,
        security=SecurityPolicy(),
        gates=[Gate(name="tests", command="pytest")],
        private_gate=PrivateGate(required=False),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["src/**"])],
    )


def test_claude_native_feature_policy_is_token_bounded() -> None:
    features = load_claude_features(ROOT / "config/claude_features.yaml")
    assert features.cross_session_messaging.enabled is True
    assert features.cross_session_messaging.max_messages_per_session <= 4
    assert features.agent_teams.enabled is False
    assert features.memory.auto_memory_enabled is False
    # The official Workflow tool is not assumed in the Python Agent SDK.
    assert features.dynamic_workflows.enabled is False


def test_trust_builder_gets_peer_channel_advisor_goal_but_no_workflow() -> None:
    features = load_claude_features(ROOT / "config/claude_features.yaml")
    roles = load_roles(ROOT / "config/roles.yaml")
    task = _task()
    stage = task.pipeline[0].model_copy(update={"model": "sonnet", "max_turns": 10})
    plan = build_session_feature_plan(
        features=features,
        task=task,
        stage=stage,
        role_config=roles[RoleName.BUILDER],
        run_id="run-12345678",
        attempt=1,
        peer_names=["rp-t999-integration-scout-12345678-a1"],
    )
    assert plan.peer_messaging is True
    assert {"ListAgents", "SendMessage"}.issubset(plan.tools)
    assert plan.advisor_model == "opus"
    assert plan.goal_condition is not None
    assert plan.workflow_name is None
    assert "Workflow" not in plan.tools
    assert plan.settings_payload["crossSessionInbound"] == "accept"
    assert plan.settings_payload["isolatePeerMachines"] is True


def test_standard_builder_avoids_expensive_claude_features() -> None:
    features = load_claude_features(ROOT / "config/claude_features.yaml")
    roles = load_roles(ROOT / "config/roles.yaml")
    task = _task(RiskTier.STANDARD)
    stage = task.pipeline[0].model_copy(update={"model": "sonnet"})
    plan = build_session_feature_plan(
        features=features,
        task=task,
        stage=stage,
        role_config=roles[RoleName.BUILDER],
        run_id="run-12345678",
        attempt=1,
        peer_names=["unused-peer"],
    )
    assert plan.peer_messaging is False
    assert plan.advisor_model is None
    assert plan.goal_condition is None
    assert plan.tools == ()
