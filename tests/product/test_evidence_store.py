from __future__ import annotations

import os
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import pytest
from traincapsule_core import digest_json
from traincapsule_core.evidence import EvidenceStoreError, LocalEvidenceStore
from traincapsule_core.models import EvidenceArtifact

CAPTURED_AT = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)


def put(store: LocalEvidenceStore, *, case_id: str = "CASE-1", payload: bytes = b"raw"):
    return store.put_bytes(
        case_id=case_id,
        payload=payload,
        kind="TRACE",
        source_adapter="fixture",
        source_version="1.0",
        captured_at=CAPTURED_AT,
        provenance={"fixture": "true"},
    )


def test_content_addressed_round_trip_is_customer_local_and_idempotent(
    tmp_path: Path,
) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    artifact = put(store)
    repeated = put(store)
    assert artifact == repeated
    assert artifact.customer_local_uri.startswith("cas://CASE-1/sha256/")
    assert artifact.artifact_id == artifact.content_digest
    assert store.get_bytes(case_id="CASE-1", artifact=artifact) == b"raw"


def test_cross_case_access_is_forbidden(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    artifact = put(store, case_id="CASE-A")
    with pytest.raises(EvidenceStoreError, match="cross-case"):
        store.get_bytes(case_id="CASE-B", artifact=artifact)


def test_unsafe_identifiers_and_symlink_roots_are_rejected(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(ValueError, match="unsafe"):
        put(store, case_id="../escape")

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked-store"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(EvidenceStoreError, match="symlink"):
        LocalEvidenceStore(link)


def test_symlink_sources_and_oversize_artifacts_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"12345")
    link = tmp_path / "source-link.bin"
    link.symlink_to(source)
    store = LocalEvidenceStore(tmp_path / "store", max_artifact_bytes=4)
    with pytest.raises(EvidenceStoreError, match="symlink"):
        store.put_file(
            source=link,
            case_id="CASE-1",
            kind="TRACE",
            source_adapter="fixture",
            source_version="1.0",
            captured_at=CAPTURED_AT,
        )
    with pytest.raises(EvidenceStoreError, match="size"):
        put(store, payload=b"12345")


def test_duplicate_metadata_conflict_and_object_substitution_are_detected(
    tmp_path: Path,
) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    artifact = put(store)
    with pytest.raises(EvidenceStoreError, match="conflicting metadata"):
        store.put_bytes(
            case_id="CASE-1",
            payload=b"raw",
            kind="DIFFERENT_KIND",
            source_adapter="fixture",
            source_version="1.0",
            captured_at=CAPTURED_AT,
        )

    digest_hex = artifact.content_digest.removeprefix("sha256:")
    object_path = tmp_path / "store/cases/CASE-1/objects/sha256" / digest_hex
    object_path.write_bytes(b"substituted")
    with pytest.raises(EvidenceStoreError, match="digest mismatch"):
        store.get_bytes(case_id="CASE-1", artifact=artifact)

    object_path.unlink()
    target = tmp_path / "attacker-controlled"
    target.write_bytes(b"raw")
    object_path.symlink_to(target)
    with pytest.raises(EvidenceStoreError, match="unsafe"):
        store.get_bytes(case_id="CASE-1", artifact=artifact)


def test_caller_cannot_replace_persisted_artifact_metadata(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    artifact = put(store)
    forged_payload = artifact.model_dump(mode="json", by_alias=True)
    forged_payload["kind"] = "CALLER_RELABELED"
    forged_payload.pop("metadataDigest")
    forged_payload["metadataDigest"] = digest_json(forged_payload)
    forged = EvidenceArtifact.model_validate(forged_payload)

    with pytest.raises(EvidenceStoreError, match="persisted metadata"):
        store.get_bytes(case_id="CASE-1", artifact=forged)

    assert store.get_artifact(case_id="CASE-1", artifact_id=artifact.artifact_id) == artifact


def test_case_artifact_count_is_bounded(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "store", max_case_artifacts=1)
    put(store, payload=b"one")
    with pytest.raises(EvidenceStoreError, match="count"):
        put(store, payload=b"two")


def test_cas_parent_symlink_swap_cannot_escape_store(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    object_root = tmp_path / "store/cases/CASE-RACE/objects/sha256"
    object_root.mkdir(parents=True)
    parked = object_root.parent / "parked"
    outside = tmp_path / "outside"
    outside.mkdir()
    stop = threading.Event()

    def swap_parent() -> None:
        while not stop.is_set():
            try:
                os.rename(object_root, parked)
                os.symlink(outside, object_root, target_is_directory=True)
                os.unlink(object_root)
                os.rename(parked, object_root)
            except OSError:
                continue

    worker = threading.Thread(target=swap_parent, daemon=True)
    worker.start()
    try:
        for attempt in range(200):
            with suppress(EvidenceStoreError):
                put(store, case_id="CASE-RACE", payload=f"race-{attempt}".encode())
        assert list(outside.iterdir()) == []
    finally:
        stop.set()
        worker.join(timeout=2)
        if object_root.is_symlink():
            object_root.unlink()
        if parked.exists() and not object_root.exists():
            os.rename(parked, object_root)
