from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import RiskTier, TaskPacket
from .util import run_command, write_json


class QualityPolicyError(RuntimeError):
    pass


_SECRET_PATTERNS = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic_secret_assignment": re.compile(
        r"(?i)(?:api[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{12,}"
    ),
}
_FORBIDDEN_FILENAMES = {
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "claude-oauth-token",
    ".credentials.json",
}
_TEST_PATH_RE = re.compile(r"(^|/)(tests?|specs?)(/|$)|(^|/)__tests__(/|$)")
# `specs/tasks/<TASK_ID>.md` is a controller-owned planning document that the
# planning pipeline itself mandates as a writable planner output (see
# `tcfactory.risk.planning_pipeline`). It is a specification narrative, not an
# executable test, so test-change authority and the private-gate requirement for
# test edits must not be applied to it; otherwise re-planning an existing task
# is structurally impossible. Every other check (secrets, status laundering,
# size, forbidden filenames) still applies to it unchanged.
_PLANNING_SPEC_RE = re.compile(r"^specs/tasks/[^/]+\.md$")
_SKIP_RE = re.compile(
    r"(?i)(pytest\.skip|pytest\.mark\.(?:skip|xfail)|unittest\.skip|@skip|\bxskip\b)"
)
# `assert True` / `assert 1` only as a complete statement (optionally with a
# message or trailing comment): `assert 1 == 1` is a real comparison, not a
# weak test, and previously matched by accident.
_WEAKEN_RE = re.compile(
    r"(?i)(assert\s+(?:true|1)\s*(?:$|[#,;])|except\s+exception\s*:\s*pass\b|#\s*noqa.*test)"
)
# Companion multi-line form: `except Exception:` with `pass` on the next line.
# Matched against a file's added lines joined with newlines; only spans that
# actually cross a newline are reported here (single-line hits are handled by
# the per-line scan above, which can classify inert fixtures).
_WEAKEN_MULTILINE_RE = re.compile(r"(?i)except\s+exception\s*:\s*\n\s*pass\b")

_UNCERTAIN_STATUS = (
    r"UNKNOWN|SKIPPED|DIVERGENCE_UNATTRIBUTED|UNATTRIBUTED|INVALID_ORACLE"
    r"|INFRASTRUCTURE_ERROR|EXTERNAL_VALIDATION_REQUIRED"
)
_PASS_STATUS = r"PASS(?:ED|ING)?|SUCCESS(?:FUL)?|SUCCEEDED"
# Symbols that convert one status into another. `==`/`!=`/`<=`/`>=` are
# comparisons, not conversions, and must not match.
_SYMBOL_OP = r"(?:->|=>|→|:=|:|(?<![=!<>])=(?!=))"
# Words that convert one status into another, as opposed to merely mentioning
# both statuses in the same sentence or evidence line.
_WORD_OP = (
    r"\b(?:as|to|into|becomes?|treat(?:ed|s)?|count(?:ed|s)?|map(?:ped|s)?"
    r"|promote[ds]?|coerce[ds]?|override[ds]?|forced?|replace[ds]?|rewrit\w*"
    r"|convert\w*|alias\w*)\b"
)
# Directional conversion: an uncertainty status, a conversion operator, then a
# pass status. `{"UNKNOWN": "PASS"}`, `INVALID_ORACLE -> PASS`,
# `treat SKIPPED as PASS`, `count X as SUCCESS`, `s = "PASS"` after `UNKNOWN:`.
_LAUNDER_DIRECTIONAL_RE = re.compile(
    rf"(?i)\b(?:{_UNCERTAIN_STATUS})\b.{{0,40}}?(?:{_SYMBOL_OP}|{_WORD_OP}).{{0,24}}?\b(?:{_PASS_STATUS})\b"
)
# Conversion call: replace("SKIPPED", "PASS") and friends, where the comma pair
# sits inside a conversion-like call. A bare list such as ["UNKNOWN", "PASS"]
# is an enumeration, not a conversion, and must not match.
_LAUNDER_CALL_RE = re.compile(
    rf"(?i)\b(?:replace|translate|convert|coerce|remap|rewrite|swap|sub)\w*\s*\("
    rf"[^()]{{0,60}}?\b(?:{_UNCERTAIN_STATUS})\b[^()]{{0,60}}?,[^()]{{0,60}}?\b(?:{_PASS_STATUS})\b"
)
# Conditional laundering: `"pass" if raw == "unknown" else raw`.
_LAUNDER_TERNARY_RE = re.compile(
    rf"(?i)\b(?:{_PASS_STATUS})\b[\"']?\s+if\b.{{0,60}}?\b(?:{_UNCERTAIN_STATUS})\b"
)
_LAUNDER_RES = (_LAUNDER_DIRECTIONAL_RE, _LAUNDER_CALL_RE, _LAUNDER_TERNARY_RE)
# A conversion can be split across lines, most commonly as an uncertainty
# guard followed by an assignment/return of PASS. Per-line matching alone
# misses this ordinary form. These two expressions are paired within a small
# diff hunk window below, and at least one participating line must be added.
_LAUNDER_GUARD_RE = re.compile(
    rf"(?i)(?:\b(?:if|elif|when|case|switch|match)\b.{{0,100}}?"
    rf"\b(?:{_UNCERTAIN_STATUS})\b[^\w\n]{{0,8}}|"
    rf"\b(?:{_UNCERTAIN_STATUS})\b[\"']?\s*:)\s*$"
)
_PASS_ACTION_RE = re.compile(
    rf"(?i)(?:\b(?:return|yield)\b|(?:->|=>|:=|(?<![=!<>])=(?!=))|"
    rf"\b(?:set|emit|report|record|write|store)\w*\s*\().{{0,48}}?"
    rf"\b(?:{_PASS_STATUS})\b"
)
# A line that reports, forbids, or excludes laundering is not itself
# laundering. The rescue below only ever applies to text that cannot execute
# (prose files, string literals, comments); live code is never rescued.
_LAUNDER_NEGATION_RE = re.compile(
    r"(?i)\b(?:not|never|no\s+longer|exclude[ds]?|excluding|without|cannot|can't"
    r"|refus\w*|reject\w*|forbid\w*|prohibit\w*|prevent\w*|guard\w*|block\w*|detect\w*"
    r"|violation\w*|must\s+remain|stays?|remains?)\b"
)
# Loose proximity heuristic retained as reviewer-visible signal, never a hard
# failure. Case-sensitive: status tokens are upper-case by convention and a
# case-insensitive version is too noisy on prose.
_STATUS_PROXIMITY_RE = re.compile(
    rf"\b(?:{_UNCERTAIN_STATUS})\b.{{0,80}}\b(?:{_PASS_STATUS})\b"
    rf"|\b(?:{_PASS_STATUS})\b.{{0,80}}\b(?:{_UNCERTAIN_STATUS})\b"
)

# Files whose lines can execute. Matches in live spans of these files are hard
# violations with no negation rescue; everything else is prose/data where a
# match cannot execute and an explicit negation downgrades it to a warning.
_CODE_SUFFIXES = {
    ".py",
    ".pyi",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".rb",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".java",
}

# The detector's own definitions and its regression fixtures must remain
# maintainable. Only inert occurrences (see `_inert_spans`) inside these
# contexts are downgraded; live code there still hard-fails.
_FIXTURE_DEFINITION_PATHS = frozenset({"tcfactory/quality_policy.py"})


def _is_code_file(path_value: str) -> bool:
    return Path(path_value).suffix.lower() in _CODE_SUFFIXES


def _is_fixture_context(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/")
    return bool(_TEST_PATH_RE.search(normalized)) or normalized in _FIXTURE_DEFINITION_PATHS


def _inert_spans(text: str, *, include_comment: bool = True) -> list[tuple[int, int]]:
    """Character spans of one added line that cannot execute: quoted string
    literals and a trailing comment. A pattern match contained in such a span
    is data (a test fixture or a detector definition), not live behaviour.

    `include_comment` is disabled for checks whose pattern is itself a comment
    directive (a `# noqa` suppression is live behaviour, not documentation).
    """
    spans: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in "\"'":
            cursor = index + 1
            while cursor < length:
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == char:
                    break
                cursor += 1
            spans.append((index + 1, min(cursor, length)))
            index = cursor + 1
            continue
        if char == "#":
            if include_comment:
                spans.append((index, length))
            break
        index += 1
    return spans


def _is_inert(text: str, match: re.Match[str], *, include_comment: bool = True) -> bool:
    start, end = match.span()
    spans = _inert_spans(text, include_comment=include_comment)
    return any(begin <= start and end <= finish for begin, finish in spans)


def _diff(worktree: Path, base_sha: str) -> str:
    return run_command(
        ["git", "diff", "--no-ext-diff", "--unified=3", base_sha],
        cwd=worktree,
        check=False,
    ).stdout


def _untracked_files(worktree: Path) -> list[str]:
    output = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=worktree, check=False
    ).stdout
    return [line for line in output.splitlines() if line]


def _added_lines(worktree: Path, diff: str) -> list[tuple[str, str]]:
    """Return (path, added line) pairs so findings can name the offending file.

    Untracked files never appear in `git diff <base>`, but the quality gate
    runs before the stage's changes are committed, so a brand-new file is
    entirely untracked at scan time. Its full content is therefore included
    here; otherwise a candidate could hide any pattern in a new file.
    """
    lines: list[tuple[str, str]] = []
    current = "<unknown file>"
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = target[2:] if target.startswith("b/") else target
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append((current, line[1:]))
    for path_value in _untracked_files(worktree):
        path = worktree / path_value
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines.extend((path_value, line) for line in text.splitlines())
    return lines


def _changed_files(worktree: Path, base_sha: str) -> list[str]:
    output = run_command(["git", "diff", "--name-only", base_sha], cwd=worktree, check=False).stdout
    return sorted({*output.splitlines(), *_untracked_files(worktree)} - {""})


def _first_launder_match(text: str) -> re.Match[str] | None:
    for pattern in _LAUNDER_RES:
        match = pattern.search(text)
        if match is not None:
            return match
    return None


def _diff_line_windows(
    worktree: Path, diff: str
) -> list[tuple[str, list[tuple[int, str, bool]]]]:
    """Return per-hunk new-file lines as (line number, text, is_added).

    Context lines let the detector see an added PASS assignment under an
    existing UNKNOWN guard. Untracked files are represented as one all-added
    window because they do not appear in ``git diff``.
    """
    windows: list[tuple[str, list[tuple[int, str, bool]]]] = []
    current_path = "<unknown file>"
    current_lines: list[tuple[int, str, bool]] | None = None
    new_line = 0
    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ "):
            target = raw_line[4:].strip()
            current_path = target[2:] if target.startswith("b/") else target
            continue
        if raw_line.startswith("@@ "):
            match = re.search(r"\+(\d+)(?:,\d+)?", raw_line)
            if match is None:
                current_lines = None
                continue
            new_line = int(match.group(1))
            current_lines = []
            windows.append((current_path, current_lines))
            continue
        if current_lines is None or not raw_line:
            continue
        prefix = raw_line[0]
        if prefix == "-" or raw_line.startswith("\\ No newline"):
            continue
        if prefix in {" ", "+"}:
            current_lines.append((new_line, raw_line[1:], prefix == "+"))
            new_line += 1

    for path_value in _untracked_files(worktree):
        path = worktree / path_value
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        windows.append(
            (path_value, [(number, line, True) for number, line in enumerate(text.splitlines(), 1)])
        )
    return windows


def _multiline_launder_findings(
    worktree: Path, diff: str
) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    warnings: list[str] = []
    for path_value, lines in _diff_line_windows(worktree, diff):
        for index, (guard_number, guard_text, guard_added) in enumerate(lines):
            guard_match = _LAUNDER_GUARD_RE.search(guard_text)
            if guard_match is None:
                continue
            for action_number, action_text, action_added in lines[index + 1 : index + 5]:
                if action_number - guard_number > 3:
                    break
                action_match = _PASS_ACTION_RE.search(action_text)
                if action_match is None or not (guard_added or action_added):
                    continue
                guard_inert = _is_inert(guard_text, guard_match)
                action_inert = _is_inert(action_text, action_match)
                snippet = (
                    f"line {guard_number}: {guard_text.strip()} / "
                    f"line {action_number}: {action_text.strip()}"
                )
                live_code = _is_code_file(path_value) and not (guard_inert and action_inert)
                combined = f"{guard_text}\n{action_text}"
                if live_code:
                    violations.append(
                        "Candidate appears to convert an uncertainty/error status into PASS "
                        f"across lines in {path_value}: {snippet[:240]}"
                    )
                elif _LAUNDER_NEGATION_RE.search(combined):
                    warnings.append(
                        "Multi-line status-conversion phrasing is negated/excluded; reviewer "
                        f"must confirm it describes prevention in {path_value}: {snippet[:240]}"
                    )
                elif _is_fixture_context(path_value) and guard_inert and action_inert:
                    warnings.append(
                        "Inert multi-line status-laundering pattern; reviewer must confirm it "
                        f"is fixture data in {path_value}: {snippet[:240]}"
                    )
                else:
                    violations.append(
                        "Candidate appears to convert an uncertainty/error status into PASS "
                        f"across lines in {path_value}: {snippet[:240]}"
                    )
                break
    return violations, warnings


def scan_candidate(
    *, worktree: Path, base_sha: str, task: TaskPacket, artifact_dir: Path
) -> dict[str, Any]:
    changed = _changed_files(worktree, base_sha)
    diff = _diff(worktree, base_sha)
    violations: list[str] = []
    warnings: list[str] = []

    test_changes = [
        path
        for path in changed
        if _TEST_PATH_RE.search(path) and not _PLANNING_SPEC_RE.match(path)
    ]
    existing_test_changes = [
        path
        for path in test_changes
        if run_command(
            ["git", "cat-file", "-e", f"{base_sha}:{path}"],
            cwd=worktree,
            check=False,
        ).returncode
        == 0
    ]
    new_test_files = sorted(set(test_changes) - set(existing_test_changes))
    if existing_test_changes and not task.allow_test_changes:
        violations.append(
            "Task is not authorized to modify existing tests: "
            f"{existing_test_changes}. Adding new tests is allowed."
        )
    if (
        test_changes
        and task.risk_tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}
        and not task.private_gate.required
    ):
        violations.append("Integration/trust-core test changes require an external private gate")

    for path_value in changed:
        path = worktree / path_value
        if Path(path_value).name in _FORBIDDEN_FILENAMES:
            violations.append(f"Forbidden secret-bearing filename changed: {path_value}")
        if path.is_file() and path.stat().st_size > 20 * 1024 * 1024:
            violations.append(f"Changed file exceeds 20 MiB: {path_value}")
        if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for name, pattern in _SECRET_PATTERNS.items():
                if pattern.search(text):
                    violations.append(f"Possible {name} in {path_value}")

    added = _added_lines(worktree, diff)
    removed_lines = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )

    for path_value, text in added:
        # Skip/weakening markers are judged per line so the finding names the
        # file, and so a quoted fixture in a fixture context (the only way to
        # write a regression test for, or extend, this very detector) is a
        # reviewer warning instead of a hard failure blocking the stage that
        # adds it. Live markers hard-fail everywhere, including test paths.
        for pattern, label, comment_is_inert in (
            (_SKIP_RE, "a skip/xfail marker", True),
            (_WEAKEN_RE, "a known weak-test or exception-swallowing pattern", False),
        ):
            match = pattern.search(text)
            if match is None:
                continue
            if _is_fixture_context(path_value) and _is_inert(
                text, match, include_comment=comment_is_inert
            ):
                warnings.append(
                    f"Inert reference to {label} in {path_value}; reviewer must confirm it is "
                    f"fixture or pattern data, not live code: {text.strip()[:160]}"
                )
            else:
                violations.append(
                    f"Candidate adds {label} in {path_value}: {text.strip()[:160]}"
                )

    # Multi-line exception swallowing (`except Exception:` newline `pass`) is
    # invisible to the per-line scan; check each file's added lines joined.
    added_by_file: dict[str, list[str]] = {}
    for path_value, text in added:
        added_by_file.setdefault(path_value, []).append(text)
    for path_value, file_lines in added_by_file.items():
        if _WEAKEN_MULTILINE_RE.search("\n".join(file_lines)):
            violations.append(
                "Candidate adds a known weak-test or exception-swallowing pattern "
                f"in {path_value}: except Exception: / pass"
            )

    for path_value, text in added:
        # Status laundering is judged per line with three severities:
        #   1. A conversion match in live code (outside every string literal
        #      and comment) of a code file is always a hard violation; wording
        #      like "not" on the same line never rescues executable code.
        #   2. A match that cannot execute (prose/data file, string literal,
        #      or comment) with an explicit negation/exclusion on the line is
        #      truthful evidence ABOUT laundering — reviewer warning.
        #   3. An inert match in a fixture context (test paths and this
        #      detector's own definitions) is fixture data — reviewer warning.
        #      This removes the self-referential trap where a regression test
        #      for this detector was itself flagged as laundering, hard-failing
        #      the very stage adding it (see factory/queue/failed/T001 history).
        #   Everything else fails closed as a violation naming file and line.
        launder_match = _first_launder_match(text)
        if launder_match is not None:
            snippet = text.strip()[:160]
            live_code = _is_code_file(path_value) and not _is_inert(text, launder_match)
            if live_code:
                violations.append(
                    "Candidate appears to convert an uncertainty/error status into PASS "
                    f"in {path_value}: {snippet}"
                )
            elif _LAUNDER_NEGATION_RE.search(text):
                warnings.append(
                    "Status-conversion phrasing is negated/excluded on the line; reviewer "
                    f"must confirm it describes prevention, not behaviour, in {path_value}: "
                    f"{snippet}"
                )
            elif _is_fixture_context(path_value) and (
                not _is_code_file(path_value) or _is_inert(text, launder_match)
            ):
                warnings.append(
                    "Inert status-laundering pattern; reviewer must confirm "
                    f"it is an inert test fixture, not live code, in {path_value}: {snippet}"
                )
            else:
                violations.append(
                    "Candidate appears to convert an uncertainty/error status into PASS "
                    f"in {path_value}: {snippet}"
                )
        elif _STATUS_PROXIMITY_RE.search(text):
            warnings.append(
                "Uncertainty and pass statuses appear together; reviewer must confirm no "
                f"status conversion in {path_value}: {text.strip()[:160]}"
            )

    multiline_violations, multiline_warnings = _multiline_launder_findings(worktree, diff)
    violations.extend(multiline_violations)
    warnings.extend(multiline_warnings)

    removed_assertions = [line for line in removed_lines.splitlines() if "assert" in line.lower()]
    if removed_assertions and not task.allow_test_changes:
        violations.append("Candidate removes assertions without test-change authority")
    elif removed_assertions:
        warnings.append(f"Removed assertions require reviewer attention: {len(removed_assertions)}")

    report = {
        "task_id": task.task_id,
        "risk_tier": task.risk_tier.value,
        "base_sha": base_sha,
        "changed_files": changed,
        "test_changes": test_changes,
        "existing_test_changes": existing_test_changes,
        "new_test_files": new_test_files,
        "violations": sorted(set(violations)),
        "warnings": warnings,
        "passed": not violations,
    }
    write_json(artifact_dir / "quality-policy.json", report)
    return report


def enforce_candidate_quality(
    *, worktree: Path, base_sha: str, task: TaskPacket, artifact_dir: Path
) -> dict[str, Any]:
    report = scan_candidate(
        worktree=worktree, base_sha=base_sha, task=task, artifact_dir=artifact_dir
    )
    if report["violations"]:
        raise QualityPolicyError("; ".join(str(x) for x in report["violations"]))
    return report
