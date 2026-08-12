from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from traincapsule_core.evidence import EvidenceStoreError, LocalEvidenceStore

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


def test_case_artifact_count_is_bounded(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "store", max_case_artifacts=1)
    put(store, payload=b"one")
    with pytest.raises(EvidenceStoreError, match="count"):
        put(store, payload=b"two")
