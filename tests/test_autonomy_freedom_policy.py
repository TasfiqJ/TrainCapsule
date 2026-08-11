from pathlib import Path

from tcfactory.autopilot import (
    _finite_ceiling_exceeded,  # pyright: ignore[reportPrivateUsage]
    _finite_ceiling_reached,  # pyright: ignore[reportPrivateUsage]
)
from tcfactory.config import load_autonomy_config

ROOT = Path(__file__).resolve().parents[1]


def test_live_autonomy_uses_work_until_done_product_limits() -> None:
    autonomy = load_autonomy_config(ROOT / "config/autonomy.yaml")
    assert autonomy.max_respecifications_per_task == 0
    assert autonomy.max_completion_expansions == 0
    assert autonomy.value_redesign_limit == 0

    assert _finite_ceiling_reached(10_000, 0) is False
    assert _finite_ceiling_exceeded(10_000, 0) is False
    assert _finite_ceiling_reached(3, 3) is True
    assert _finite_ceiling_exceeded(4, 3) is True


def test_planners_are_instructed_to_deliver_complete_sellable_outcomes() -> None:
    global_prompt = (ROOT / "prompts/global.md").read_text(encoding="utf-8")
    autonomous = (ROOT / "prompts/autonomous_planner.md").read_text(encoding="utf-8")
    planner = (ROOT / "prompts/task_packet_planner.md").read_text(encoding="utf-8")

    assert "complete founder-level product and company brief" in global_prompt
    assert "smallest *complete sellable outcome*" in global_prompt
    assert "as many acceptance criteria as necessary" in autonomous
    assert "Agent sub-agents are encouraged" in autonomous
    assert "without an arbitrary numeric cap" in planner
    assert "ordinary product and engineering decisions" in planner
