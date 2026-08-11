from __future__ import annotations

from tcfactory.context import newest_unique_findings


def test_previous_findings_are_newest_first_and_deduplicated() -> None:
    durable_history = [
        "old counterexample",
        "repeated gate failure",
        "new repair evidence",
        "repeated gate failure",
        "  newest reviewer finding  ",
    ]

    prioritized = newest_unique_findings(durable_history)

    assert prioritized == [
        "newest reviewer finding",
        "repeated gate failure",
        "new repair evidence",
        "old counterexample",
    ]
    assert durable_history == [
        "old counterexample",
        "repeated gate failure",
        "new repair evidence",
        "repeated gate failure",
        "  newest reviewer finding  ",
    ]
