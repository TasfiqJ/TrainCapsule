"""Regression tests for the uncertainty-status laundering detector.

Durable failure reproduced: factory/queue/failed/T001.error.txt recorded
"Every bounded Sonnet/Opus repair cycle failed ... Last stage error: Candidate
appears to convert an uncertainty/error status into PASS". The T001 candidate
(4f9aa0a..c1518a0) only recorded raw evidence lines that mention an uncertainty
status and a pass status in the same sentence, including a negative control
that proves laundering is detected. The old proximity regex flagged those
verbatim evidence lines, so no evidence-recording task could ever pass, and
every repair to this detector was rejected by the detector itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tcfactory.gitops import commit_all, current_sha
from tcfactory.models import RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.quality_policy import QualityPolicyError, enforce_candidate_quality
from tcfactory.util import run_command

# Verbatim added lines from the T001 candidate diff that must not hard-fail.
# The first four are the confirmed false positives from
# context/T001-research-a5-quality-policy.json.
T001_EVIDENCE_LINES = [
    "NB1 through NB4 verified; NB5 is UNKNOWN and excluded from the pass set.",
    "INVALID_ORACLE. The valid PASS is a separate, correctly invoked run, not a reinterpretation",
    "EC4: PASS - 23 truth_state field(s), unknown_vocabulary=[], pass_with_nonzero_exit=[]",
    "[EC5] an UNKNOWN behaviour is aggregated into the pass summary: DETECTED",
    "NB5 is UNKNOWN and is excluded from the pass set; see SOURCE_PRECEDENCE.md section 7.",
    "Not laundered: NB5 stays UNKNOWN; 10 UNKNOWN, 5 EXTERNAL_VALIDATION_REQUIRED, 0 SKIPPED.",
    "| NB5 | UNKNOWN | NB1 | PASS |",
    "Totals: 3 PASS, 1 UNKNOWN",
]

# Genuine conversions that must stay hard violations in production code.
LAUNDERING_LINES = [
    '    "UNKNOWN": "PASS",',
    '    if state == "UNKNOWN": state = "PASS"',
    'status = status.replace("INFRASTRUCTURE_ERROR", "PASS")',
    "# treat SKIPPED as PASS for the summary",
    "INVALID_ORACLE -> PASS",
    'truth_state = "pass" if raw == "unknown" else raw',
    "count EXTERNAL_VALIDATION_REQUIRED as SUCCESS",
    "UNATTRIBUTED => PASSED",
    'STATUS_ALIASES = {"SKIPPED": "SUCCESS"}',
]

MULTILINE_LAUNDERING_BODIES = [
    'if state == "UNKNOWN":\n    state = "PASS"\n',
    'case "SKIPPED":\n    return "SUCCESS"\n',
    'if result == "INVALID_ORACLE":\n    emit_status("PASSED")\n',
]


def _repo(path: Path) -> str:
    run_command(["git", "init", "-b", "main"], cwd=path)
    run_command(["git", "config", "user.name", "Test User"], cwd=path)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=path)
    (path / "app.py").write_text("x = 1\n")
    commit_all(path, "start")
    return current_sha(path)


def _task() -> TaskPacket:
    return TaskPacket(
        task_id="T900",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["README.md"],
        acceptance_criteria=["works"],
        outputs=["app.py"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["**"])],
    )


def _scan(
    tmp_path: Path, relative: str, body: str, *, commit: bool = True
) -> dict[str, Any]:
    base = _repo(tmp_path)
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    if commit:
        commit_all(tmp_path, "candidate")
    return enforce_candidate_quality(
        worktree=tmp_path,
        base_sha=base,
        task=_task(),
        artifact_dir=tmp_path / "artifacts",
    )


def test_raw_evidence_with_mixed_statuses_is_not_a_violation(tmp_path: Path) -> None:
    report = _scan(
        tmp_path,
        "docs/evidence/T001/raw/nb_checker.txt",
        "\n".join(T001_EVIDENCE_LINES) + "\n",
    )
    assert report["violations"] == []
    assert report["passed"] is True


@pytest.mark.parametrize("line", T001_EVIDENCE_LINES)
def test_each_recorded_evidence_line_passes(tmp_path: Path, line: str) -> None:
    report = _scan(tmp_path, "docs/evidence/raw.txt", line + "\n")
    assert report["violations"] == []


@pytest.mark.parametrize("line", LAUNDERING_LINES)
def test_status_conversion_still_fails_closed(tmp_path: Path, line: str) -> None:
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "tcfactory/summary.py", line + "\n")


@pytest.mark.parametrize("line", LAUNDERING_LINES)
def test_status_conversion_in_uncommitted_new_file_still_fails(
    tmp_path: Path, line: str
) -> None:
    """The gate runs before the stage's changes are committed, so a brand-new
    file is untracked and absent from `git diff <base>`. Its content must be
    scanned anyway; otherwise any pattern can hide in a new file.
    """
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "tcfactory/summary.py", line + "\n", commit=False)


@pytest.mark.parametrize("body", MULTILINE_LAUNDERING_BODIES)
def test_multiline_status_conversion_still_fails_closed(tmp_path: Path, body: str) -> None:
    with pytest.raises(QualityPolicyError, match="across lines"):
        _scan(tmp_path, "tcfactory/summary.py", body)


@pytest.mark.parametrize("body", MULTILINE_LAUNDERING_BODIES)
def test_multiline_status_conversion_in_untracked_file_still_fails(
    tmp_path: Path, body: str
) -> None:
    with pytest.raises(QualityPolicyError, match="across lines"):
        _scan(tmp_path, "tcfactory/summary.py", body, commit=False)


def test_added_pass_action_under_existing_unknown_guard_still_fails(tmp_path: Path) -> None:
    _repo(tmp_path)
    target = tmp_path / "tcfactory" / "summary.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('if state == "UNKNOWN":\n    state = state\n')
    commit_all(tmp_path, "guard baseline")
    base = current_sha(tmp_path)
    target.write_text('if state == "UNKNOWN":\n    state = "PASS"\n')
    with pytest.raises(QualityPolicyError, match="across lines"):
        enforce_candidate_quality(
            worktree=tmp_path,
            base_sha=base,
            task=_task(),
            artifact_dir=tmp_path / "artifacts",
        )


def test_separate_multiline_status_counts_are_not_a_conversion(tmp_path: Path) -> None:
    report = _scan(
        tmp_path,
        "docs/evidence/counts.txt",
        "UNKNOWN count: 3\nPASS count: 5\n",
    )
    assert report["violations"] == []


def test_violation_names_the_offending_file_and_line(tmp_path: Path) -> None:
    with pytest.raises(QualityPolicyError) as excinfo:
        _scan(tmp_path, "tcfactory/summary.py", 'STATE = {"UNKNOWN": "PASS"}\n')
    message = str(excinfo.value)
    assert "tcfactory/summary.py" in message
    assert '"UNKNOWN": "PASS"' in message


def test_negation_comment_cannot_rescue_live_conversion_code(tmp_path: Path) -> None:
    """Wording like "not" on the same line must never downgrade executable
    conversion code, or a candidate could launder a status by appending a
    trailing comment such as `# not laundering`.
    """
    body = 'if s == "UNKNOWN": s = "PASS"  # not laundering, reviewed\n'
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "tcfactory/summary.py", body)


def test_negation_comment_cannot_rescue_live_conversion_in_test_path(tmp_path: Path) -> None:
    body = 'state = "PASS" if state == "UNKNOWN" else state  # never launders\n'
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "tests/helpers/shim.py", body)


def test_status_enumeration_list_is_not_a_conversion(tmp_path: Path) -> None:
    """A bare list naming both statuses is an enumeration, not a mapping."""
    report = _scan(tmp_path, "tcfactory/statuses.py", 'STATUSES = ["UNKNOWN", "PASS"]\n')
    assert report["violations"] == []
    assert any("reviewer must confirm no status conversion" in w for w in report["warnings"])


def test_equality_comparisons_are_not_conversions(tmp_path: Path) -> None:
    """`==` comparisons legitimately mention both statuses on one line."""
    body = 'ok = result == "PASS" and other == "UNKNOWN"\n'
    report = _scan(tmp_path, "tcfactory/checks.py", body)
    assert report["violations"] == []
    assert any("reviewer must confirm no status conversion" in w for w in report["warnings"])


def test_ambiguous_proximity_is_surfaced_as_a_reviewer_warning(tmp_path: Path) -> None:
    report = _scan(tmp_path, "docs/evidence/table.md", "| UNKNOWN | PASS |\n")
    assert report["violations"] == []
    assert any("reviewer must confirm no status conversion" in w for w in report["warnings"])
    assert any("docs/evidence/table.md" in w for w in report["warnings"])


def test_word_boundaries_ignore_identifiers(tmp_path: Path) -> None:
    body = "unknown_vocabulary=[], pass_with_nonzero_exit=[]\n"
    report = _scan(tmp_path, "docs/evidence/fields.txt", body)
    assert report["violations"] == []
    assert report["warnings"] == []


def test_new_regression_test_file_with_laundering_fixtures_does_not_hard_fail(
    tmp_path: Path,
) -> None:
    """A stage that adds a regression test for this detector (containing the
    exact positive fixtures a detector must catch) must not be blocked by
    scanning its own diff. Without this, no fresh session could ever land a
    correct regression test for laundering detection: the fixture lines would
    always trip the hard check on the stage's own added test file, hard-failing
    the very stage that adds them.
    """
    fixture_lines = "\n".join(f"    {line!r}," for line in LAUNDERING_LINES)
    body = f"LAUNDERING_LINES = [\n{fixture_lines}\n]\n"
    report = _scan(tmp_path, "tests/test_new_detector_fixture.py", body)
    assert report["violations"] == []
    assert report["passed"] is True
    assert any("inert test fixture" in w for w in report["warnings"])


def test_detector_can_extend_its_own_fixture_file(tmp_path: Path) -> None:
    """Meta-regression for the bootstrap trap: adding an inert positive fixture
    to this very test file must produce warnings only, so the detector's own
    regression suite can keep growing under the detector's supervision.
    """
    fixture_lines = "\n".join(f"    {line!r}," for line in LAUNDERING_LINES)
    body = f"LAUNDERING_LINES = [\n{fixture_lines}\n]\n"
    report = _scan(tmp_path, "tests/test_status_launder_detection.py", body, commit=False)
    assert report["violations"] == []
    assert report["passed"] is True


def test_live_status_conversion_in_a_test_path_still_hard_fails(tmp_path: Path) -> None:
    """The downgrade is for inert data only. Executable conversion code under a
    test path -- where the match straddles the quoted literals instead of
    sitting inside one -- must remain a hard violation, so the carve-out cannot
    be used to launder a status by moving the code under tests/.
    """
    body = 'def normalize(state):\n    if state == "UNKNOWN": state = "PASS"\n    return state\n'
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "tests/helpers/status_shim.py", body)


def test_new_regression_test_for_the_skip_detector_does_not_hard_fail(
    tmp_path: Path,
) -> None:
    """Same self-referential trap, one detector over: the skip/xfail check ran
    over the whole added diff, so a stage that added a regression test
    containing skip-marker fixtures hard-failed its own diff with a finding
    that named no file. Quoted fixtures are now reviewer warnings naming the file.
    """
    body = 'SKIP_FIXTURES = [\n    "pytest.skip(\'x\')",\n    "@pytest.mark.xfail",\n]\n'
    report = _scan(tmp_path, "tests/test_skip_detector.py", body)
    assert report["violations"] == []
    assert report["passed"] is True
    assert any(
        "Inert reference to a skip/xfail marker" in w and "tests/test_skip_detector.py" in w
        for w in report["warnings"]
    )


def test_extending_the_detector_definition_is_not_self_blocked(tmp_path: Path) -> None:
    """Maintaining the detector's own pattern definitions must stay possible:
    the marker text only appears inside a regex string literal there.
    """
    body = '_SKIP_RE = re.compile(r"(pytest\\.skip|@skip|@pytest.mark.skipif)")\n'
    report = _scan(tmp_path, "tcfactory/quality_policy.py", body)
    assert report["violations"] == []
    assert any("Inert reference to a skip/xfail marker" in w for w in report["warnings"])


def test_live_skip_marker_is_still_a_hard_violation_in_a_test_file(tmp_path: Path) -> None:
    body = "import pytest\n\n\n@pytest.mark.skip\ndef test_thing():\n    assert 2 == 2\n"
    with pytest.raises(QualityPolicyError) as excinfo:
        _scan(tmp_path, "tests/test_live_skip.py", body)
    assert "Candidate adds a skip/xfail marker in tests/test_live_skip.py" in str(excinfo.value)


def test_noqa_test_suppression_comment_is_still_a_hard_violation(tmp_path: Path) -> None:
    """A lint-suppression comment is live behaviour, not documentation, so the
    comment carve-out must not apply to the weakening check even in a test file.
    """
    body = "def test_thing():\n    value = compute()  # noqa: F821 test\n"
    with pytest.raises(QualityPolicyError, match="weak-test or exception-swallowing"):
        _scan(tmp_path, "tests/test_suppressed.py", body)


def test_live_skip_marker_in_production_code_is_still_a_hard_violation(
    tmp_path: Path,
) -> None:
    body = "def run():\n    unittest.skip('later')\n"
    with pytest.raises(QualityPolicyError, match="skip/xfail marker in tcfactory/summary.py"):
        _scan(tmp_path, "tcfactory/summary.py", body)


def test_multiline_exception_swallowing_is_still_a_hard_violation(tmp_path: Path) -> None:
    """`except Exception:` with `pass` on the next line was caught by the old
    concatenated scan; the per-line scan must not lose it.
    """
    body = "def run():\n    try:\n        work()\n    except Exception:\n        pass\n"
    with pytest.raises(QualityPolicyError, match="weak-test or exception-swallowing"):
        _scan(tmp_path, "tcfactory/runner.py", body)


def test_real_assertions_comparing_literals_are_not_weak_tests(tmp_path: Path) -> None:
    """`assert 1 == 1` is a real comparison; only bare `assert True` / `assert 1`
    statements are the weak-test pattern.
    """
    body = "def test_x():\n    assert 1 == 1\n"
    report = _scan(tmp_path, "tests/test_new.py", body, commit=False)
    assert report["violations"] == []


def test_bare_assert_true_is_still_a_weak_test(tmp_path: Path) -> None:
    body = "def test_x():\n    assert True\n"
    with pytest.raises(QualityPolicyError, match="weak-test or exception-swallowing"):
        _scan(tmp_path, "tests/test_lazy.py", body)


def test_laundering_in_a_production_file_still_hard_fails_even_with_test_changes(
    tmp_path: Path,
) -> None:
    """The test-file carve-out must stay scoped to test paths; production code
    that launders a status is still a hard violation regardless of what else
    changed."""
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "tcfactory/summary.py", 'STATE = {"UNKNOWN": "PASS"}\n')


def test_laundering_in_a_config_file_still_hard_fails(tmp_path: Path) -> None:
    """Data files can drive behaviour; a status alias in config is a violation."""
    with pytest.raises(QualityPolicyError, match="uncertainty/error status into PASS"):
        _scan(tmp_path, "config/statuses.json", '{"UNKNOWN": "PASS"}\n')
