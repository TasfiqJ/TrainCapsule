from __future__ import annotations

import pytest
from traincapsule_verifier.ruleset_policy import validate_release_rule_types


def test_bypass_free_direct_main_release_rules_are_accepted() -> None:
    validate_release_rule_types({"non_fast_forward", "deletion"})


def test_pr_rules_are_rejected_because_they_block_direct_main() -> None:
    with pytest.raises(ValueError, match="incompatible with direct"):
        validate_release_rule_types(
            {
                "pull_request",
                "non_fast_forward",
                "deletion",
            }
        )


def test_incomplete_release_rules_are_rejected() -> None:
    with pytest.raises(ValueError, match="missing required release controls"):
        validate_release_rule_types({"non_fast_forward"})
