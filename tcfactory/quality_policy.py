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
_SKIP_RE = re.compile(
    r"(?i)(pytest\.skip|pytest\.mark\.(?:skip|xfail)|unittest\.skip|@skip|\bxskip\b)"
)
_WEAKEN_RE = re.compile(
    r"(?i)(assert\s+true\b|assert\s+1\b|except\s+exception\s*:\s*pass|#\s*noqa.*test)"
)
_STATUS_LAUNDER_RE = re.compile(
    r"(?i)(UNKNOWN|SKIPPED|DIVERGENCE_UNATTRIBUTED|INVALID_ORACLE|INFRASTRUCTURE_ERROR).{0,80}(PASS|SUCCESS)"
)


def _diff(worktree: Path, base_sha: str) -> str:
    return run_command(
        ["git", "diff", "--no-ext-diff", "--unified=1", base_sha],
        cwd=worktree,
        check=False,
    ).stdout


def _changed_files(worktree: Path, base_sha: str) -> list[str]:
    output = run_command(["git", "diff", "--name-only", base_sha], cwd=worktree, check=False).stdout
    untracked = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=worktree, check=False
    ).stdout
    return sorted({*output.splitlines(), *untracked.splitlines()} - {""})


def scan_candidate(
    *, worktree: Path, base_sha: str, task: TaskPacket, artifact_dir: Path
) -> dict[str, Any]:
    changed = _changed_files(worktree, base_sha)
    diff = _diff(worktree, base_sha)
    violations: list[str] = []
    warnings: list[str] = []

    test_changes = [path for path in changed if _TEST_PATH_RE.search(path)]
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

    added_lines = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    removed_lines = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )
    if _SKIP_RE.search(added_lines):
        violations.append("Candidate adds a skip/xfail marker")
    if _WEAKEN_RE.search(added_lines):
        violations.append("Candidate adds a known weak-test or exception-swallowing pattern")
    if _STATUS_LAUNDER_RE.search(added_lines):
        violations.append("Candidate appears to convert an uncertainty/error status into PASS")
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
