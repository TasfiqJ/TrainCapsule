#!/usr/bin/env python3
"""Reject human intervention and pull-request publication in active V3.1 policy."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.source_authority import validate_active_source_generation  # noqa: E402

ACTIVE_DIRECTORY_PATTERNS = (
    "prompts/**/*.md",
    "config/**/*.json",
    "config/**/*.yaml",
    "config/**/*.yml",
    "factory/policy/**/*.json",
    "factory/policy/**/*.yaml",
    "factory/roadmap/milestones.yaml",
    "factory/roadmap/work_items.yaml",
    "factory/roadmap/dispositions.yaml",
    "schemas/factory/v3/**/*.json",
    "tcfactory/**/*.py",
    "scripts/**/*.py",
    "scripts/**/*.ps1",
    "scripts/**/*.sh",
)
ACTIVE_FILES = (
    "README.md",
    "docs/CONTEXT_INDEX.yaml",
    "tcfactory/completion.py",
    "tcfactory/context.py",
    "tcfactory/github_sync.py",
    "tcfactory/runtime_status.py",
    "tcfactory/supervisor.py",
)
SELF_PATH = "scripts/gates/active_policy_integrity.py"
NON_RUNTIME_GENERATORS = {"scripts/generate_v3_1_zh_source.py"}
HISTORICAL_POLICY_FILES = {
    "config/owner_directives.yaml",
    "factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json",
}
ALLOWED_EXACT_LINES: dict[str, set[str]] = {
    "tcfactory/context.py": {
        '                "supersedes human-approval and PR-first clauses only",'
    },
}

FORBIDDEN = (
    ("waiting-human state", re.compile(r"\bWAITING_HUMAN\b")),
    ("human-reviewer owner", re.compile(r"\bHUMAN_REVIEWER\b")),
    ("human owner enum", re.compile(r"\bOwnerType\.HUMAN\b")),
    ("human milestone enum", re.compile(r"\bMilestoneStatus\.WAITING_HUMAN\b")),
    ("human finding owner", re.compile(r"ownerClass[^\n]{0,80}\bHUMAN\b", re.IGNORECASE)),
    (
        "enabled pull-request release",
        re.compile(
            r"AUTOMATED_PR_REQUIRED|automated_pull_request_required\s*:\s*Literal\[True\]|"
            r"OPEN_AUTOMATED_PULL_REQUEST|candidateBranchPrefix|pullRequestMetadataPath",
            re.IGNORECASE,
        ),
    ),
    (
        "required human approval",
        re.compile(
            r"(?:qualified\s+)?human approvals?\s+(?:is|are|remain|must be)?\s*"
            r"(?:required|required to|exist)",
            re.IGNORECASE,
        ),
    ),
)
class ActivePolicyError(RuntimeError):
    pass


def active_policy_files(repo_root: Path) -> list[Path]:
    paths = {repo_root / relative for relative in ACTIVE_FILES}
    validate_active_source_generation(repo_root)
    for pattern in ACTIVE_DIRECTORY_PATTERNS:
        paths.update(repo_root.glob(pattern))
    return sorted(
        path
        for path in paths
        if path.is_file()
        and path.relative_to(repo_root).as_posix()
        not in {SELF_PATH, *NON_RUNTIME_GENERATORS, *HISTORICAL_POLICY_FILES}
    )


def validate_active_policy(repo_root: Path) -> int:
    active_source = validate_active_source_generation(repo_root)
    manifest = (repo_root / active_source.manifest_path).read_text(encoding="utf-8")
    if active_source.generation_id not in manifest:
        raise ActivePolicyError("active policy manifest does not declare its generation")

    violations: list[str] = []
    scanned = active_policy_files(repo_root)
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(repo_root).as_posix()
        for label, pattern in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                line_text = text.splitlines()[line - 1]
                if line_text in ALLOWED_EXACT_LINES.get(relative, set()):
                    continue
                violations.append(f"{relative}:{line}: {label}")
    if violations:
        raise ActivePolicyError("active policy residue:\n" + "\n".join(sorted(violations)))
    return len(scanned)


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ROOT
    if len(sys.argv) > 2:
        raise SystemExit("usage: active_policy_integrity.py [REPOSITORY_ROOT]")
    try:
        count = validate_active_policy(repo_root)
    except (OSError, ValueError, ActivePolicyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {count} active policy files contain no human or direct-main dependency")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
