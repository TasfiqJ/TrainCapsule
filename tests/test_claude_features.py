from pathlib import Path

from tcfactory.claude_features import (
    build_session_feature_plan,
    load_claude_features,
    should_launch_scout,
)
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


def test_claude_native_feature_policy_enables_renewable_production_work() -> None:
    features = load_claude_features(ROOT / "config/claude_features.yaml")
    roles = load_roles(ROOT / "config/roles.yaml")
    assert features.cross_session_messaging.enabled is True
    assert features.cross_session_messaging.max_messages_per_session <= 10
    assert features.agent_teams.enabled is True
    assert features.memory.auto_memory_enabled is True
    # The normal Agent tool is available; the separate Workflow tool is not assumed.
    assert features.dynamic_workflows.enabled is False
    scout = roles[RoleName.INTEGRATION_SCOUT]
    assert scout.max_turns >= 20
    assert scout.task_budget_tokens is None
    assert features.integration_scout.blocking_on_non_pass is True


def test_scout_prompt_prioritizes_peer_discovery_before_inspection() -> None:
    prompt = (ROOT / "prompts/integration_scout.md").read_text(encoding="utf-8")

    discovery = prompt.index("make peer discovery and the required handshake your first action")
    inspection = prompt.index("Inspect the frozen task")
    assert discovery < inspection


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
    assert "evaluated turns" not in plan.goal_condition
    assert "renewable controller sessions" in plan.goal_condition
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


def test_integration_builder_gets_independent_integration_scout() -> None:
    features = load_claude_features(ROOT / "config/claude_features.yaml")
    task = _task(RiskTier.INTEGRATION)
    assert RiskTier.INTEGRATION in features.integration_scout.risk_tiers
    assert should_launch_scout(features, task, task.pipeline[0]) is True
