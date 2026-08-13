"""Typed, deterministic V2-to-V3 migration mapping records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, cast

from pydantic import Field, model_validator

from tcfactory.feature_ledger import load_feature_ledger
from tcfactory.util import atomic_write_text
from tcfactory.v3.base import (
    DIGEST_PATTERN,
    SHA_PATTERN,
    V3Model,
    sha256_digest,
)
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

V3WorkItemId = Annotated[str, Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")]

# Historical evidence records the state-directory roster that existed when the
# immutable V2 queue archive was captured. Later runtime statuses must not
# rewrite that receipt retroactively.
LEGACY_ARCHIVE_V3_STATE_DIRECTORIES = (
    "blocked_policy",
    "blocked_technical",
    "cancelled",
    "completed",
    "deferred",
    "native_sufficient",
    "passed_engineering",
    "paused_quota",
    "proposed",
    "queued",
    "ready",
    "rejected_value",
    "running",
    "superseded",
    "waiting_external",
    "waiting_human",
)


class LegacyStatus(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    PACKET_PROPOSED = "packet_proposed"
    PACKET_APPROVED = "packet_approved"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    EXTERNAL_WAIT = "external_wait"
    PASSED = "passed"
    FAILED = "failed"
    RESPEC_REQUIRED = "respec_required"
    DEFERRED = "deferred"


class LegacyDisposition(StrEnum):
    FACTORY = "FACTORY"
    MAPPED_TO_V3 = "MAPPED_TO_V3"
    DEFERRED_DESIGN = "DEFERRED_DESIGN"
    DEFERRED_NON_BLOCKING = "DEFERRED_NON_BLOCKING"


class LegacyMapRecord(V3Model):
    legacy_task_id: str = Field(pattern=r"^T[0-9]{3}$")
    legacy_status: LegacyStatus
    legacy_outcome: str = Field(min_length=1)
    legacy_packet: str | None = None
    v3_disposition: LegacyDisposition
    mapped_work_items: list[V3WorkItemId]
    reason: str = Field(min_length=1)
    evidence_preserved: list[str]

    @model_validator(mode="after")
    def validate_disposition(self) -> LegacyMapRecord:
        if len(self.mapped_work_items) != len(set(self.mapped_work_items)):
            raise ValueError("mapped V3 work item IDs must be unique per legacy task")
        if self.mapped_work_items != sorted(self.mapped_work_items):
            raise ValueError("mapped V3 work item IDs must be sorted")
        if len(self.evidence_preserved) != len(set(self.evidence_preserved)):
            raise ValueError("preserved evidence references must be unique")
        if self.evidence_preserved != sorted(self.evidence_preserved):
            raise ValueError("preserved evidence references must be sorted")
        if self.v3_disposition is LegacyDisposition.MAPPED_TO_V3 and not self.mapped_work_items:
            raise ValueError("MAPPED_TO_V3 requires at least one V3 work item")
        if (
            self.v3_disposition
            in {
                LegacyDisposition.DEFERRED_DESIGN,
                LegacyDisposition.DEFERRED_NON_BLOCKING,
            }
            and self.mapped_work_items
        ):
            raise ValueError("deferred legacy work cannot activate V3 work items")
        return self


class LegacyEvidenceFile(V3Model):
    path: str = Field(min_length=1)
    mode: str = Field(pattern=r"^[0-7]{4}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LegacyMigrationMap(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    source_version: int = Field(default=2, ge=2, le=2)
    migration_base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_ledger_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    source_policy_ref: str = Field(min_length=1)
    records: list[LegacyMapRecord]
    preserved_evidence_inventory: list[LegacyEvidenceFile] = Field(min_length=1)
    preserved_evidence_inventory_digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    @model_validator(mode="after")
    def unique_mapping(self) -> LegacyMigrationMap:
        legacy_ids = [record.legacy_task_id for record in self.records]
        if len(legacy_ids) != len(set(legacy_ids)):
            raise ValueError("legacy task IDs must be unique")
        expected = [f"T{index:03d}" for index in range(1, 125)]
        if legacy_ids != expected:
            raise ValueError("legacy migration must contain ordered T001 through T124")
        paths = [item.path for item in self.preserved_evidence_inventory]
        if paths != sorted(set(paths)):
            raise ValueError("legacy evidence inventory paths must be unique and sorted")
        payload = b"".join(
            f"{item.mode}\0{item.path}\0{item.sha256}\n".encode()
            for item in self.preserved_evidence_inventory
        )
        if sha256_digest(payload) != self.preserved_evidence_inventory_digest:
            raise ValueError("legacy evidence inventory digest mismatch")
        return self

    def validate_v3_targets(self, known_work_items: set[str]) -> None:
        mapped = {
            work_item_id for record in self.records for work_item_id in record.mapped_work_items
        }
        missing = mapped - known_work_items
        if missing:
            raise ValueError(f"legacy migration has unknown V3 targets: {sorted(missing)}")


def verify_stopped_legacy_queue(
    repo_root: Path, *, require_live: bool = False
) -> tuple[str, datetime]:
    """Verify live V2 queue bytes when present, otherwise its tracked snapshot receipt."""
    snapshot_path = repo_root / "docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json"
    raw_snapshot: object = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(raw_snapshot, dict):
        raise ValueError("runtime snapshot must be an object")
    snapshot = cast(dict[str, object], raw_snapshot)
    queue = snapshot.get("queue")
    if not isinstance(queue, dict):
        raise ValueError("runtime snapshot queue must be an object")
    queue = cast(dict[str, object], queue)
    summary = queue.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("runtime snapshot queue summary must be an object")
    summary = cast(dict[str, object], summary)
    if summary.get("running") != []:
        raise ValueError("runtime snapshot does not prove an empty running queue")
    declared = queue.get("files")
    if not isinstance(declared, list):
        raise ValueError("runtime snapshot queue files must be a list")

    expected: dict[str, tuple[int, str]] = {}
    for raw in cast(list[object], declared):
        if not isinstance(raw, dict):
            raise ValueError("runtime snapshot queue file must be an object")
        raw = cast(dict[str, object], raw)
        path = raw.get("path")
        size = raw.get("bytes")
        digest = raw.get("sha256")
        if not isinstance(path, str) or not isinstance(size, int) or not isinstance(digest, str):
            raise ValueError("runtime snapshot queue file fields are invalid")
        expected[path] = (size, digest)

    state_root = repo_root / "factory/state"
    queue_root = repo_root / "factory/queue"
    live_controls = (state_root / "STOP").is_file() and (state_root / "PAUSE").is_file()
    live_queue = queue_root.is_dir()
    if require_live and (not live_controls or not live_queue):
        raise ValueError("legacy queue migration requires live STOP, PAUSE, and queue evidence")
    if live_controls and live_queue:
        actual_paths = sorted(path for path in queue_root.rglob("*") if path.is_file())
        actual = {
            path.relative_to(repo_root).as_posix(): (
                path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in actual_paths
        }
    else:
        actual = expected
    if actual != expected:
        raise ValueError("live V2 queue differs from the stopped-runtime snapshot")

    hasher = hashlib.sha256()
    for path, (size, digest) in sorted(actual.items()):
        hasher.update(path.encode("utf-8") + b"\0")
        hasher.update(digest.encode("ascii") + b"\0")
        hasher.update(str(size).encode("ascii") + b"\n")
    captured_raw = snapshot.get("capturedAt")
    if not isinstance(captured_raw, str):
        raise ValueError("runtime snapshot capturedAt must be a timestamp")
    captured_at = datetime.fromisoformat(captured_raw.replace("Z", "+00:00"))
    if captured_at.tzinfo is None:
        raise ValueError("runtime snapshot capturedAt must be timezone-aware")
    return hasher.hexdigest(), captured_at.astimezone(UTC)


def archive_stopped_legacy_queue(repo_root: Path) -> Path:
    """Create an idempotent, non-resuming V2 queue archive in the V3 namespace."""

    queue_digest, captured_at = verify_stopped_legacy_queue(repo_root)
    timestamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
    queue = V3Queue(repo_root / "factory/state/v3-queue")
    queue.initialize()
    target = queue.archive_v2(
        repo_root / "factory/queue",
        archive_id=f"v2-{timestamp}-{queue_digest[:12]}",
        captured_at=captured_at,
    )
    manifest_path = target / "ARCHIVE_MANIFEST.json"
    raw_manifest: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, dict):
        raise ValueError("legacy queue archive manifest must be an object")
    manifest = cast(dict[str, object], raw_manifest)
    snapshot_raw: object = json.loads(
        (repo_root / "docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(snapshot_raw, dict):
        raise ValueError("runtime snapshot must be an object")
    snapshot = cast(dict[str, object], snapshot_raw)
    receipt: dict[str, object] = {
        "version": 3,
        "migrationBaseSha": snapshot.get("head"),
        "snapshotCapturedAt": captured_at.isoformat(),
        "sourceQueue": "factory/queue",
        "archivePath": target.relative_to(repo_root).as_posix(),
        "queueSnapshotDigest": f"sha256:{queue_digest}",
        "archiveSourceDigest": manifest.get("sourceDigest"),
        "archiveManifestDigest": sha256_digest(manifest_path.read_bytes()),
        "files": manifest.get("files"),
        "originalQueueRetained": True,
        "autoResume": False,
        "v3StateDirectories": list(LEGACY_ARCHIVE_V3_STATE_DIRECTORIES),
        "stopControlPresent": (repo_root / "factory/state/STOP").is_file(),
        "pauseControlPresent": (repo_root / "factory/state/PAUSE").is_file(),
    }
    receipt_path = repo_root / "docs/migrations/V3_LEGACY_QUEUE_ARCHIVE_METADATA.json"
    rendered_receipt = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if not receipt_path.is_file() or (receipt_path.read_text(encoding="utf-8") != rendered_receipt):
        atomic_write_text(receipt_path, rendered_receipt, keep_previous=True)
    return target


def verify_legacy_queue_archive_receipt(
    repo_root: Path, *, require_live: bool = False
) -> dict[str, object]:
    """Verify the receipt plus live archive bytes, or its canonical tracked manifest."""

    receipt_path = repo_root / "docs/migrations/V3_LEGACY_QUEUE_ARCHIVE_METADATA.json"
    raw_receipt: object = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(raw_receipt, dict):
        raise ValueError("legacy queue archive receipt must be an object")
    receipt = cast(dict[str, object], raw_receipt)
    if (
        receipt.get("version") != 3
        or receipt.get("autoResume") is not False
        or receipt.get("originalQueueRetained") is not True
        or receipt.get("stopControlPresent") is not True
        or receipt.get("pauseControlPresent") is not True
    ):
        raise ValueError("legacy queue archive receipt violates stopped-state policy")
    if receipt.get("v3StateDirectories") != list(LEGACY_ARCHIVE_V3_STATE_DIRECTORIES):
        raise ValueError("legacy queue archive historical state roster mismatch")
    archive_raw = receipt.get("archivePath")
    if not isinstance(archive_raw, str):
        raise ValueError("legacy queue archive receipt lacks archivePath")
    archive = (repo_root / archive_raw).resolve()
    archive_root = (repo_root / "factory/state/v3-queue/archive/v2").resolve()
    if not archive.is_relative_to(archive_root):
        raise ValueError("legacy queue archive path escapes")

    raw_files = receipt.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("legacy queue archive receipt files must be a list")
    source_root = repo_root / "factory/queue"
    normalized_files: list[dict[str, str | int]] = []
    for raw_file in cast(list[object], raw_files):
        if not isinstance(raw_file, dict):
            raise ValueError("legacy queue archive receipt file must be an object")
        record = cast(dict[str, object], raw_file)
        relative = record.get("path")
        digest = record.get("sha256")
        size = record.get("bytes")
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or not isinstance(size, int)
        ):
            raise ValueError("legacy queue archive receipt file fields are invalid")
        normalized_files.append({"path": relative, "sha256": digest, "bytes": size})
        source = (source_root / relative).resolve()
        copied = (archive / relative).resolve()
        if not source.is_relative_to(source_root.resolve()) or not copied.is_relative_to(archive):
            raise ValueError("legacy queue archive receipt file path escapes")
        if require_live or (source.is_file() and copied.is_file()):
            for path in (source, copied):
                if not path.is_file():
                    raise ValueError(f"legacy queue archive evidence is missing: {relative}")
                payload = path.read_bytes()
                if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
                    raise ValueError(f"legacy queue archive evidence mismatch: {relative}")

    captured_at = receipt.get("snapshotCapturedAt")
    source_digest = receipt.get("archiveSourceDigest")
    if not isinstance(captured_at, str) or not isinstance(source_digest, str):
        raise ValueError("legacy queue archive receipt lacks canonical manifest fields")
    manifest = {
        "archiveId": archive.name,
        "autoResume": False,
        "capturedAt": captured_at,
        "files": normalized_files,
        "sourceDigest": source_digest,
        "sourceLabel": "queue",
        "version": 3,
    }
    canonical_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    expected_manifest_digest = receipt.get("archiveManifestDigest")
    if expected_manifest_digest != sha256_digest(canonical_manifest):
        raise ValueError("legacy queue archive canonical manifest digest mismatch")
    manifest_path = archive / "ARCHIVE_MANIFEST.json"
    if (require_live or manifest_path.is_file()) and (
        not manifest_path.is_file() or manifest_path.read_bytes() != canonical_manifest
    ):
        raise ValueError("legacy queue archive live manifest mismatch")
    return receipt


def load_installed_legacy_migration(repo_root: Path) -> LegacyMigrationMap:
    """Verify the committed V2 archive and mapping against both source ledgers."""

    source_path = repo_root / "factory/feature_ledger.yaml"
    archive_path = repo_root / "factory/roadmap/legacy_feature_ledger.yaml"
    mapping_path = repo_root / "factory/roadmap/migrations/v2_to_v3.yaml"
    if archive_path.read_bytes() != source_path.read_bytes():
        raise ValueError("legacy feature ledger archive differs from its V2 source")
    migration = LegacyMigrationMap.model_validate(load_yaml(mapping_path))
    if migration.source_ledger_digest != sha256_digest(source_path.read_bytes()):
        raise ValueError("legacy migration source digest does not match the V2 ledger")

    source = load_feature_ledger(source_path)
    if migration.source_policy_ref != source.source_of_truth:
        raise ValueError("legacy migration source policy reference does not match")
    for item, record in zip(source.tasks, migration.records, strict=True):
        if (
            record.legacy_task_id != item.task_id
            or record.legacy_status.value != item.status
            or record.legacy_outcome != item.outcome
            or record.legacy_packet != item.packet_path
        ):
            raise ValueError(f"legacy migration record differs for {item.task_id}")

    roadmap = WorkItemCollection.model_validate(
        load_yaml(repo_root / "factory/roadmap/work_items.yaml")
    )
    migration.validate_v3_targets({item.work_item_id for item in roadmap.work_items})
    return migration
