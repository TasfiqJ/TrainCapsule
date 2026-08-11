from __future__ import annotations

from pathlib import Path

from tcfactory.autopilot import (
    is_external_evidence_block,
    is_infrastructure_failure,
    sync_ledger_from_queue,
    terminal_blocker_reason,
    terminal_root_blocker,
    visible_blocked_task_ids,
)
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


def test_external_evidence_block_waits_without_spending_a_respecification(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    item = ledger.item("T002")
    item.packet_path = "tasks/T002.yaml"
    item.status = "packet_approved"
    config = FactoryConfig()
    blocked = queue_dirs(tmp_path, config)["blocked"] / "T002.yaml"
    blocked.write_text("task_id: T002\n", encoding="utf-8")
    blocked.with_suffix(".error.txt").write_text(
        "PipelineBlocked: External value evidence is required and cannot be "
        "manufactured by the autonomous builder.\n",
        encoding="utf-8",
    )

    assert sync_ledger_from_queue(tmp_path, config, ledger)
    assert item.status == "external_wait"
    assert item.evidence == ["factory/queue/blocked/T002.error.txt"]
    assert visible_blocked_task_ids(ledger) == ["T002", "T003"]
    assert item.revisions == 0


def test_only_canonical_external_evidence_blocks_enter_external_wait() -> None:
    assert is_external_evidence_block("EXTERNAL_EVIDENCE_REQUIRED")
    assert is_external_evidence_block("External value evidence is required")
    assert not is_external_evidence_block("ordinary reviewer rejection")


def test_external_wait_without_queue_residue_still_has_a_truthful_ui_reason(
    tmp_path: Path,
) -> None:
    item = _ledger().item("T003")
    item.evidence = ["evidence/external/T003.json"]

    reason = terminal_blocker_reason(tmp_path, FactoryConfig(), item)

    assert "independently attributable external evidence" in reason
    assert "evidence/external/T003.json" in reason


def test_terminal_blocked_queue_entry_stays_terminal(tmp_path: Path) -> None:
    ledger = _ledger()
    item = ledger.item("T002")
    item.packet_path = "tasks/T002.yaml"
    item.status = "blocked"
    item.terminal_blocked = True
    config = FactoryConfig()
    blocked = queue_dirs(tmp_path, config)["blocked"] / "T002.yaml"
    blocked.write_text("task_id: T002\n", encoding="utf-8")

    assert not sync_ledger_from_queue(tmp_path, config, ledger)
    assert item.status == "blocked"
    assert ledger.next_ready() is None


def test_only_terminal_root_cause_is_reported_and_repaired() -> None:
    ledger = _ledger()
    root = ledger.item("T001")
    root.status = "blocked"
    root.terminal_blocked = True
    dependent = ledger.item("T002")
    dependent.status = "blocked"

    assert terminal_root_blocker(ledger) is root
    assert visible_blocked_task_ids(ledger) == ["T001", "T003"]


def test_stale_main_and_turn_limits_are_infrastructure_failures() -> None:
    assert is_infrastructure_failure("Cannot resume T001: main moved from abc to def")
    assert is_infrastructure_failure("Reached maximum number of turns (18)")
    assert not is_infrastructure_failure("material-value gate rejected the result")
    # "no repair path remains" is the pipeline's own control-flow wrapper, emitted for
    # any role that has no assigned repair stage. It is not evidence of an
    # infrastructure fault, and matching it granted every truthful stage rejection a
    # requeue that does not consume a re-specification revision. A genuine turn ceiling
    # is still recovered because pipeline.terminal_failure_message now embeds the
    # stage's own error in that wrapper; see tests/test_terminal_failure_signal.py.
    assert not is_infrastructure_failure("Stage research failed and no repair path remains")
