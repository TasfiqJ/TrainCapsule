from pathlib import Path

from tcfactory.autopilot import (
    _finite_ceiling_exceeded,  # pyright: ignore[reportPrivateUsage]
    _finite_ceiling_reached,  # pyright: ignore[reportPrivateUsage]
)
from tcfactory.config import load_autonomy_config

ROOT = Path(__file__).resolve().parents[1]


def test_live_autonomy_uses_finite_v3_limits() -> None:
    autonomy = load_autonomy_config(ROOT / "config/autonomy.yaml")
    assert autonomy.max_respecifications_per_task == 2
    assert autonomy.max_completion_expansions == 1
    assert autonomy.value_redesign_limit == 1
    assert autonomy.auto_merge is False
    assert autonomy.enabled is False

    assert _finite_ceiling_reached(3, 3) is True
    assert _finite_ceiling_exceeded(4, 3) is True


def test_planners_are_instructed_to_deliver_complete_sellable_outcomes() -> None:
    global_prompt = (ROOT / "prompts/global.md").read_text(encoding="utf-8")
    autonomous = (ROOT / "prompts/autonomous_planner.md").read_text(encoding="utf-8")
    planner = (ROOT / "prompts/task_packet_planner.md").read_text(encoding="utf-8")

    assert "real production product" in global_prompt
    assert "smallest complete sellable outcome" in global_prompt
    assert "living plan" in autonomous
    assert "one Claude owner" in autonomous
    assert "no more than 12 acceptance criteria" in planner
    assert "ordinary product and engineering decisions" in planner
