from tcfactory.models import RoleName, StageResult, Verdict
from tcfactory.pipeline import apply_scout_verdict


def _result(role: RoleName, verdict: Verdict) -> StageResult:
    return StageResult(
        task_id="DEMO-001",
        run_id="run",
        role=role,
        attempt=1,
        model="sonnet",
        verdict=verdict,
        artifact_dir="artifacts",
    )


def test_required_unknown_scout_prevents_builder_pass() -> None:
    builder = _result(RoleName.BUILDER, Verdict.PASS)
    scout = _result(RoleName.INTEGRATION_SCOUT, Verdict.UNKNOWN)

    apply_scout_verdict(
        builder,
        scout,
        blocking_on_concrete_failure=True,
        blocking_on_non_pass=True,
    )

    assert builder.verdict == Verdict.UNKNOWN
    assert builder.error is not None
    assert "independent peer evidence is required" in builder.error


def test_required_failed_scout_fails_builder() -> None:
    builder = _result(RoleName.BUILDER, Verdict.PASS)
    scout = _result(RoleName.INTEGRATION_SCOUT, Verdict.FAIL)

    apply_scout_verdict(
        builder,
        scout,
        blocking_on_concrete_failure=True,
        blocking_on_non_pass=True,
    )

    assert builder.verdict == Verdict.FAIL
    assert builder.error is not None
    assert "concrete blocking contradiction" in builder.error


def test_passing_scout_preserves_builder_pass() -> None:
    builder = _result(RoleName.BUILDER, Verdict.PASS)
    scout = _result(RoleName.INTEGRATION_SCOUT, Verdict.PASS)

    apply_scout_verdict(
        builder,
        scout,
        blocking_on_concrete_failure=True,
        blocking_on_non_pass=True,
    )

    assert builder.verdict == Verdict.PASS
    assert builder.error is None
