from __future__ import annotations

from pathlib import Path

from tcfactory.autopilot import sync_ledger_from_queue
from tcfactory.feature_ledger import FeatureItem, FeatureLedger
from tcfactory.models import FactoryConfig
from tcfactory.queue import queue_dirs


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


def test_failed_task_remains_routed_to_respecification() -> None:
    ledger = _ledger()
    failed = ledger.item("T002")
    failed.status = "respec_required"
    failed.packet_path = "tasks/T002.yaml"

    ledger.refresh_readiness()

    assert failed.status == "respec_required"
    assert ledger.next_ready() is None


def test_terminal_block_does_not_reenter_the_ready_queue() -> None:
    ledger = _ledger()
    blocked = ledger.item("T002")
    blocked.terminal_blocked = True
    blocked.packet_path = "tasks/T002.yaml"

    ledger.refresh_readiness()

    assert blocked.status == "blocked"
    assert ledger.next_ready() is None


def test_queue_block_routes_to_autonomous_respecification(tmp_path: Path) -> None:
    ledger = _ledger()
    item = ledger.item("T002")
    item.packet_path = "tasks/T002.yaml"
    item.status = "packet_approved"
    config = FactoryConfig()
    blocked = queue_dirs(tmp_path, config)["blocked"] / "T002.yaml"
    blocked.write_text("task_id: T002\n", encoding="utf-8")

    assert sync_ledger_from_queue(tmp_path, config, ledger)
    assert item.status == "respec_required"
    assert ledger.next_ready() is None
