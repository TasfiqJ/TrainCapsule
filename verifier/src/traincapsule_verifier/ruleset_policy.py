"""Exact release-ruleset semantics shared by verifier entrypoints."""

from __future__ import annotations

from collections.abc import Set

REQUIRED_RELEASE_RULE_TYPES = frozenset(
    {
        "required_status_checks",
        "pull_request",
        "non_fast_forward",
        "deletion",
    }
)
FORBIDDEN_RELEASE_RULE_TYPES = frozenset({"update"})


def validate_release_rule_types(rule_types: Set[str]) -> None:
    """Require PR-only controls without GitHub's merge-deadlocking update rule."""

    missing = REQUIRED_RELEASE_RULE_TYPES - rule_types
    if missing:
        raise ValueError(f"ruleset is missing required release controls: {sorted(missing)}")
    forbidden = FORBIDDEN_RELEASE_RULE_TYPES & rule_types
    if forbidden:
        raise ValueError(
            "GitHub restrict-updates is incompatible with a bypass-free automated PR ruleset "
            "and would block PR merges"
        )
