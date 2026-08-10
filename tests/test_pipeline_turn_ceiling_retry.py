"""Regression: a turn ceiling must not burn the whole bounded retry budget.

Provenance limitation: this module previously cited ``factory/state/pipelines/T001.json``
as verbatim durable evidence. That file does not exist in this worktree, and the only
on-disk T001 failure artifact
(``factory/recovery/task-packets/T001-infrastructure-max-turns.error.txt``) records only
the generic wrapper ``Stage research failed and no repair path remains.`` -- the stage's
own error was discarded before it was persisted. The constant below is therefore a
representative SDK turn-ceiling string, not a transcription of an attributed T001
attempt, and these tests are boundary tests of the classifier rather than evidence about
what actually failed in T001.
"""

from __future__ import annotations

from tcfactory.models import RoleConfig, RoleName, Stage, StageResult, Verdict
from tcfactory.pipeline import (
    MAX_REVIEW_TURN_MULTIPLIER,
    MAX_STAGE_TURNS,
    escalated_turn_budget,
    retry_stage_update,
    review_turn_retry_update,
    stage_hit_turn_ceiling,
)

# Representative SDK turn-ceiling error text; see the module docstring's provenance note.
T001_TURN_CEILING_ERROR = (
    "Exception: Claude Code returned an error result: "
    "Reached maximum number of turns (18)"
)


def _result(**overrides: object) -> StageResult:
    fields: dict[str, object] = {
        "task_id": "T001",
        "run_id": "20260810T162445Z",
        "role": RoleName.RESEARCH,
        "attempt": 1,
        "model": "opus",
        "verdict": Verdict.FAIL,
        "artifact_dir": "factory/artifacts/T001/20260810T162445Z/research-a1",
    }
    fields.update(overrides)
    return StageResult.model_validate(fields)


def _role_config(max_turns: int = 25) -> RoleConfig:
    return RoleConfig(
        prompt_file="prompts/research.md",
        model="opus",
        max_turns=max_turns,
        tools=["Read"],
    )


def test_sdk_turn_ceiling_error_text_is_recognized() -> None:
    # The report-continuation path rescues a structured report, so terminal_reason
    # reads "completed" while the durable error still records the ceiling.
    result = _result(error=T001_TURN_CEILING_ERROR, terminal_reason="completed")
    assert stage_hit_turn_ceiling(result) is True


def test_sdk_max_turns_terminal_reason_is_recognized() -> None:
    assert stage_hit_turn_ceiling(_result(terminal_reason="max_turns")) is True
    assert stage_hit_turn_ceiling(_result(error="subtype=error_max_turns")) is True


def test_truthful_product_rejection_is_not_a_turn_ceiling() -> None:
    result = _result(
        error="Candidate appears to convert an uncertainty/error status into PASS",
        terminal_reason="completed",
    )
    assert stage_hit_turn_ceiling(result) is False


def test_retry_after_turn_ceiling_raises_the_stage_turn_budget() -> None:
    stage = Stage(role=RoleName.RESEARCH, model="opus", max_turns=18)
    result = _result(error=T001_TURN_CEILING_ERROR, terminal_reason="completed")

    update = retry_stage_update(stage, result, _role_config(), "sonnet")

    assert update["model"] == "sonnet"
    assert update["max_turns"] == 36
    replacement = stage.model_copy(update=update)
    assert replacement.max_turns is not None
    assert stage.max_turns is not None
    assert replacement.max_turns > stage.max_turns


def test_retry_without_turn_ceiling_keeps_the_original_turn_budget() -> None:
    stage = Stage(role=RoleName.RESEARCH, model="opus", max_turns=18)
    result = _result(error="Acceptance criterion 3 has no attributable evidence")

    update = retry_stage_update(stage, result, _role_config(), "sonnet")

    assert update == {"model": "sonnet"}


def test_stage_without_explicit_turns_escalates_from_the_role_default() -> None:
    stage = Stage(role=RoleName.RESEARCH, model="opus")
    result = _result(terminal_reason="max_turns")

    update = retry_stage_update(stage, result, _role_config(max_turns=25), "sonnet")

    assert update["max_turns"] == 50


def test_escalation_is_bounded_by_the_stage_schema_ceiling() -> None:
    assert escalated_turn_budget(150) == MAX_STAGE_TURNS
    assert escalated_turn_budget(MAX_STAGE_TURNS) is None
    # The escalated value must remain constructible as a Stage field.
    stage = Stage(role=RoleName.RESEARCH, max_turns=escalated_turn_budget(150))
    assert stage.max_turns == MAX_STAGE_TURNS


def test_escalated_budget_never_shrinks_a_stage() -> None:
    for current in (1, 6, 18, 25, 99):
        assert (escalated_turn_budget(current) or current) > current


def test_truncated_review_is_retried_as_the_same_independent_role() -> None:
    stage = Stage(role=RoleName.ADVERSARY, model="opus", max_turns=10)
    result = _result(
        role=RoleName.ADVERSARY,
        error="Reached maximum number of turns (10)",
    )

    update = review_turn_retry_update(stage, result, _role_config(max_turns=10))

    assert update == {"max_turns": 20}
    replacement = stage.model_copy(update=update)
    assert replacement.role == RoleName.ADVERSARY
    assert replacement.model == "opus"


def test_review_retry_is_bounded_to_four_times_its_declared_budget() -> None:
    result = _result(
        role=RoleName.ADVERSARY,
        terminal_reason="max_turns",
    )
    role_config = _role_config(max_turns=10)

    assert review_turn_retry_update(
        Stage(role=RoleName.ADVERSARY, max_turns=20),
        result,
        role_config,
    ) == {"max_turns": 40}
    assert review_turn_retry_update(
        Stage(
            role=RoleName.ADVERSARY,
            max_turns=10 * MAX_REVIEW_TURN_MULTIPLIER,
        ),
        result,
        role_config,
    ) is None


def test_truthful_review_rejection_still_routes_to_normal_repair() -> None:
    stage = Stage(role=RoleName.ADVERSARY, model="opus", max_turns=10)
    result = _result(
        role=RoleName.ADVERSARY,
        error="Candidate weakens a private truth gate",
    )

    assert review_turn_retry_update(stage, result, _role_config(max_turns=10)) is None
