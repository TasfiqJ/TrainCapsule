from __future__ import annotations

import pytest
from traincapsule_verifier.ruleset_policy import validate_release_rule_types


def test_bypass_free_pr_release_rules_are_accepted() -> None:
    validate_release_rule_types(
        {"required_status_checks", "pull_request", "non_fast_forward", "deletion"}
    )


def test_restrict_updates_is_rejected_because_it_blocks_pr_merges() -> None:
    with pytest.raises(ValueError, match="would block PR merges"):
        validate_release_rule_types(
            {
                "required_status_checks",
                "pull_request",
                "non_fast_forward",
                "deletion",
                "update",
            }
        )


def test_incomplete_release_rules_are_rejected() -> None:
    with pytest.raises(ValueError, match="missing required release controls"):
        validate_release_rule_types({"non_fast_forward", "deletion"})
