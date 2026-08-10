"""Regression: a terminal PipelineFailure must carry the stage's own failure signal.

Durable evidence in this worktree: ``factory/recovery/task-packets/
T001-infrastructure-max-turns.error.txt`` contains exactly

    PipelineFailure: Stage research failed and no repair path remains.

and nothing else. The stage's real ``error``/``terminal_reason`` was discarded by the
generic terminal wrapper, so that artifact cannot be attributed: whether research hit a
turn ceiling or returned a truthful product rejection is unrecoverable from it. The
filename claims ``max-turns``; the file content does not support that claim.

The controller's earlier workaround was to hardcode that exact wrapper sentence into
``is_infrastructure_failure``, which made *every* role's "no repair path remains"
failure eligible for a free requeue that does not consume a re-specification revision.
These tests pin the replacement: the signal is preserved at the raise site, and the
classifier keys on the stage's genuine signal rather than on wrapper text.
"""

from __future__ import annotations

from tcfactory.autopilot import is_infrastructure_failure
from tcfactory.models import RoleName, StageResult, Verdict
from tcfactory.pipeline import (
    TURN_CEILING_MARKERS,
    terminal_failure_message,
    terminal_failure_signal,
)

# The wrapper text of the durable T001 artifact, with the trailing period it carries.
T001_WRAPPER_TEXT = "Stage research failed and no repair path remains."


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


def test_stage_error_is_preferred_then_terminal_reason_then_unknown() -> None:
    assert terminal_failure_signal(_result(error="boom", terminal_reason="max_turns")) == "boom"
    assert terminal_failure_signal(_result(terminal_reason="max_turns")) == "max_turns"
    assert terminal_failure_signal(_result()) == "unknown"


def test_terminal_message_keeps_the_wrapper_and_appends_the_signal() -> None:
    message = terminal_failure_message(
        T001_WRAPPER_TEXT,
        _result(error="Reached maximum number of turns (18)"),
    )
    # The operator-facing wrapper is not lost, and the classifiable signal is added.
    assert message.startswith(T001_WRAPPER_TEXT)
    assert "Reached maximum number of turns (18)" in message


def test_genuine_turn_ceiling_survives_the_terminal_wrapper() -> None:
    """The exact information loss that made the T001 artifact unattributable."""

    result = _result(error="Reached maximum number of turns (18)")
    assert is_infrastructure_failure(terminal_failure_message(T001_WRAPPER_TEXT, result)) is True


def test_wrapper_text_alone_is_not_an_infrastructure_failure() -> None:
    """A control-flow wrapper is not evidence of an infrastructure fault.

    Classifying it as one grants a free requeue to any truthful stage rejection that
    happens to have no assigned repair role, which defeats the re-specification ceiling
    that exists to surface genuine product failures.
    """

    assert is_infrastructure_failure(f"PipelineFailure: {T001_WRAPPER_TEXT}") is False


def test_unattributable_terminal_failure_is_not_recovered_for_free() -> None:
    message = terminal_failure_message(T001_WRAPPER_TEXT, _result())
    assert "unknown" in message
    assert is_infrastructure_failure(message) is False


def test_truthful_product_rejection_survives_the_terminal_wrapper() -> None:
    result = _result(error="material-value gate rejected the result")
    assert is_infrastructure_failure(terminal_failure_message(T001_WRAPPER_TEXT, result)) is False


def test_turn_ceiling_markers_are_shared_with_the_recovery_classifier() -> None:
    """Pins the two classifiers together so a future edit cannot silently desynchronize.

    ``pipeline.py`` decides whether to escalate a turn budget and retry;
    ``autopilot.py`` decides whether the same failure is recoverable without burning a
    revision. If one list gains a marker the other lacks, a turn ceiling is retried but
    never recovered (or the reverse).
    """

    assert len(TURN_CEILING_MARKERS) > 0
    for marker in TURN_CEILING_MARKERS:
        assert is_infrastructure_failure(marker) is True
