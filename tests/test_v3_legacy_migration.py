from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from scripts.generate_v3_legacy_migration import (
    build_mapping,
    rendered_mapping,
    verify_installed,
)
from tcfactory.cli import app
from tcfactory.feature_ledger import load_feature_ledger
from tcfactory.util import sha256_file
from tcfactory.v3.enums import WorkStatus
from tcfactory.v3.migrations import (
    LEGACY_ARCHIVE_V3_STATE_DIRECTORIES,
    LegacyDisposition,
    LegacyMigrationMap,
    load_installed_legacy_migration,
    verify_legacy_queue_archive_receipt,
    verify_stopped_legacy_queue,
)
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_all_124_legacy_entries_and_statuses_are_preserved_exactly() -> None:
    source_path = ROOT / "factory/feature_ledger.yaml"
    archive_path = ROOT / "factory/roadmap/legacy_feature_ledger.yaml"
    source = load_feature_ledger(source_path)
    migration = build_mapping(ROOT)

    assert archive_path.read_bytes() == source_path.read_bytes()
    assert len(source.tasks) == len(migration.records) == 124
    assert [record.legacy_task_id for record in migration.records] == [
        f"T{index:03d}" for index in range(1, 125)
    ]
    assert {
        record.legacy_task_id: record.legacy_status.value
        for record in migration.records
    } == {item.task_id: item.status for item in source.tasks}
    assert Counter(record.legacy_status.value for record in migration.records) == {
        "blocked": 120,
        "external_wait": 2,
        "passed": 1,
        "paused": 1,
    }
    assert migration.source_ledger_digest == (
        "sha256:ab5d10c6718d3a9fdf53dd78cf0c387e995cd1723cf10b76fb53e14af559c994"
    )


def test_mapping_is_explicit_bounded_and_never_resumes_t002() -> None:
    migration = build_mapping(ROOT)
    by_id = {record.legacy_task_id: record for record in migration.records}
    assert Counter(record.v3_disposition for record in migration.records) == {
        LegacyDisposition.DEFERRED_DESIGN: 29,
        LegacyDisposition.DEFERRED_NON_BLOCKING: 1,
        LegacyDisposition.FACTORY: 6,
        LegacyDisposition.MAPPED_TO_V3: 88,
    }
    assert by_id["T001"].legacy_status.value == "passed"
    assert by_id["T002"].legacy_status.value == "paused"
    assert by_id["T002"].v3_disposition is LegacyDisposition.DEFERRED_NON_BLOCKING
    assert by_id["T002"].mapped_work_items == []
    assert by_id["T002"].legacy_packet == "tasks/T002.yaml"
    assert "factory/artifacts/T002" in by_id["T002"].evidence_preserved
    assert "specs/tasks/T002.md" in by_id["T002"].evidence_preserved
    assert "never auto-resumes" in by_id["T002"].reason
    assert sha256_file(ROOT / "tasks/T002.yaml") == (
        "b11bb3d937ad0b85c7406076b577bcdaa6e4e3afcdd8a3fd4c7cc8a7ddbb0d04"
    )
    checklist = load_yaml(ROOT / "factory/policy/T002_LEGAL_CLEARANCE_CHECKLIST.yaml")
    assert checklist["status"] == "DEFERRED"
    assert checklist["blocksProductImplementation"] is False
    assert checklist["completionPolicy"]["humanInterventionRequired"] is False
    assert all(
        "factory/feature_ledger.yaml" in record.evidence_preserved
        for record in migration.records
    )
    inventory = {item.path: item for item in migration.preserved_evidence_inventory}
    for relative in (
        "tasks/T002.yaml",
        "specs/tasks/T002.md",
        "factory/recovery/task-packets/T002-r1.yaml",
    ):
        if (ROOT / relative).is_file():
            assert inventory[relative].sha256 == sha256_file(ROOT / relative)


def test_preserved_evidence_inventory_detects_byte_tamper(tmp_path: Path) -> None:
    copied = tmp_path / "repo"
    shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(".git", ".venv", "worktrees"))
    target = copied / "specs/tasks/T002.md"
    target.write_bytes(target.read_bytes() + b"\ntampered\n")
    with pytest.raises(ValueError, match="stopped-runtime snapshot|stale"):
        verify_installed(copied)


def test_mapping_targets_only_existing_v3_work_and_legacy_ids_never_enter_graph() -> None:
    migration = build_mapping(ROOT)
    roadmap = WorkItemCollection.model_validate(
        load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    )
    known = {item.work_item_id for item in roadmap.work_items}
    migration.validate_v3_targets(known)
    assert all(
        dependency.startswith("V3-")
        for item in roadmap.work_items
        for dependency in (*item.depends_on, *item.soft_depends_on)
    )
    assert all(
        item.status is not WorkStatus.RUNNING for item in roadmap.work_items
    )


def test_checked_in_mapping_is_model_valid_and_deterministic() -> None:
    path = ROOT / "factory/roadmap/migrations/v2_to_v3.yaml"
    parsed = LegacyMigrationMap.model_validate(load_yaml(path))
    assert parsed == build_mapping(ROOT)
    assert path.read_text(encoding="utf-8") == rendered_mapping(ROOT)
    verify_installed(ROOT)
    assert load_installed_legacy_migration(ROOT) == parsed


def test_stopped_queue_still_matches_snapshot_without_mutation() -> None:
    queue_root = ROOT / "factory/queue"
    before = {
        path.relative_to(queue_root).as_posix(): path.read_bytes()
        for path in queue_root.rglob("*")
        if path.is_file()
    }
    digest, captured_at = verify_stopped_legacy_queue(ROOT)
    after = {
        path.relative_to(queue_root).as_posix(): path.read_bytes()
        for path in queue_root.rglob("*")
        if path.is_file()
    }
    assert digest == "885df1dd93b8adce0876cd15f74a2921cb92f668fdc9bc24df27d56f638d3283"
    assert captured_at.isoformat() == "2026-08-11T21:20:24+00:00"
    assert before == after


def test_non_resuming_queue_archive_receipt_is_fully_verifiable() -> None:
    receipt = verify_legacy_queue_archive_receipt(ROOT)
    assert receipt["autoResume"] is False
    assert receipt["originalQueueRetained"] is True
    assert receipt["stopControlPresent"] is True
    assert receipt["pauseControlPresent"] is True
    files = receipt["files"]
    state_directories = receipt["v3StateDirectories"]
    assert isinstance(files, list) and len(cast(list[object], files)) == 3
    assert isinstance(state_directories, list)
    assert cast(list[str], state_directories) == list(LEGACY_ARCHIVE_V3_STATE_DIRECTORIES)
    assert WorkStatus.PAUSED_BACKEND.value.lower() not in cast(list[str], state_directories)


def test_tracked_queue_receipts_verify_in_a_clean_checkout(tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    (clean / "docs/migrations").mkdir(parents=True)
    for name in (
        "V3_RUNTIME_SNAPSHOT_METADATA.json",
        "V3_LEGACY_QUEUE_ARCHIVE_METADATA.json",
    ):
        shutil.copy2(ROOT / "docs/migrations" / name, clean / "docs/migrations" / name)

    digest, captured_at = verify_stopped_legacy_queue(clean)
    receipt = verify_legacy_queue_archive_receipt(clean)
    assert digest == "885df1dd93b8adce0876cd15f74a2921cb92f668fdc9bc24df27d56f638d3283"
    assert captured_at.isoformat() == "2026-08-11T21:20:24+00:00"
    assert receipt["archiveManifestDigest"] == (
        "sha256:c30a6a4b7438649a05802192927ff3c5e5b4501c8a2e5066600eb86ccab1c6d1"
    )
    with pytest.raises(ValueError, match="live STOP, PAUSE, and queue evidence"):
        verify_stopped_legacy_queue(clean, require_live=True)
    with pytest.raises(ValueError, match="evidence is missing"):
        verify_legacy_queue_archive_receipt(clean, require_live=True)


def test_exact_roadmap_migration_cli_dry_run_is_read_only() -> None:
    mapping = ROOT / "factory/roadmap/migrations/v2_to_v3.yaml"
    queue_root = ROOT / "factory/queue"
    before_mapping = mapping.read_bytes()
    before_queue = {
        path.relative_to(queue_root).as_posix(): path.read_bytes()
        for path in queue_root.rglob("*")
        if path.is_file()
    }
    runner = CliRunner()
    assert runner.invoke(app, ["migrate-roadmap", "--dry-run"]).exit_code == 2
    result = runner.invoke(
        app,
        [
            "migrate-roadmap",
            "--from-v2",
            "--dry-run",
            "--repo",
            str(ROOT),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"legacyRecords": 124' in result.output
    assert '"mutation": false' in result.output.lower()
    assert mapping.read_bytes() == before_mapping
    assert {
        path.relative_to(queue_root).as_posix(): path.read_bytes()
        for path in queue_root.rglob("*")
        if path.is_file()
    } == before_queue
