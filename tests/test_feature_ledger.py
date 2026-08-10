from __future__ import annotations

from tcfactory.feature_ledger import FeatureItem, FeatureLedger


def _ledger() -> FeatureLedger:
    return FeatureLedger(
        source_of_truth="master.md",
        tasks=[
            FeatureItem(
                task_id="T001",
                outcome="one",
                lead_role="Builder",
                phase="Phase 0",
                status="passed",
            ),
            FeatureItem(
                task_id="T002",
                outcome="two",
                lead_role="Builder",
                phase="Phase 0",
                depends_on=["T001"],
                status="blocked",
            ),
            FeatureItem(
                task_id="T003",
                outcome="external",
                lead_role="External",
                phase="Phase X",
                status="external_wait",
                automatable=False,
                completion_kind="external_validation",
            ),
        ],
    )


def test_readiness_follows_dependencies() -> None:
    ledger = _ledger()
    ledger.refresh_readiness()
    assert ledger.item("T002").status == "ready"
    assert ledger.next_ready() is not None
    assert ledger.next_ready().task_id == "T002"  # type: ignore[union-attr]


def test_external_wait_does_not_block_product_build_completion() -> None:
    ledger = _ledger()
    ledger.item("T002").status = "passed"
    assert ledger.build_complete()
