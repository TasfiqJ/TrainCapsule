"""Exact release-ruleset semantics shared by verifier entrypoints."""

from __future__ import annotations

from collections.abc import Set

REQUIRED_RELEASE_RULE_TYPES = frozenset({"non_fast_forward", "deletion"})
FORBIDDEN_RELEASE_RULE_TYPES = frozenset(
    {"update", "pull_request", "required_status_checks"}
)


def validate_release_rule_types(rule_types: Set[str]) -> None:
    """Require main-only fast-forward controls without PR dependencies."""

    missing = REQUIRED_RELEASE_RULE_TYPES - rule_types
    if missing:
        raise ValueError(f"ruleset is missing required release controls: {sorted(missing)}")
    forbidden = FORBIDDEN_RELEASE_RULE_TYPES & rule_types
    if forbidden:
        raise ValueError(
            "ruleset controls are incompatible with direct fast-forward main publication"
        )
