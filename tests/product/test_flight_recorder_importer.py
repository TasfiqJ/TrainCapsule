from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from traincapsule_core.evidence import LocalEvidenceStore
from traincapsule_core.models import NativeConfidence
from traincapsule_ingest_pytorch import (
    FlightRecorderImportError,
    ImportErrorCode,
    PyTorchFlightRecorderImporter,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "examples/product/flight-recorder"
CAPTURED_AT = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)


def test_supported_fixture_preserves_native_observations_and_unknown_fields(
    tmp_path: Path,
) -> None:
    store = LocalEvidenceStore(tmp_path / "store")
    result = PyTorchFlightRecorderImporter().import_trace(
        trace_dir=FIXTURES / "supported",
        case_id="CASE-SUPPORTED",
        store=store,
        captured_at=CAPTURED_AT,
    )
    assert result.source_format_version == "1.0"
    assert result.pytorch_version == "2.5.1"
    assert result.world_size == 2
    assert result.missing_ranks == []
    assert [(entry.rank, entry.state) for entry in result.entries] == [
        (0, "completed"),
        (1, "started"),
    ]
    assert result.entries[0].unknown_fields == {"vendorExtension": "preserved"}
    assert result.metadata_unknown_fields == {"fixtureExtension": "preserved"}
    assert result.native_findings[0].confidence_class is NativeConfidence.DIRECT_OBSERVATION
    assert "does not infer root cause" in result.native_findings[0].limitations[0]
    assert len(result.raw_digests) == len(result.artifacts) == 3
    for artifact in result.artifacts:
        assert store.get_bytes(case_id=result.case_id, artifact=artifact)


def test_unsupported_version_has_exact_error_and_raw_evidence_is_already_hashed(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "store"
    with pytest.raises(FlightRecorderImportError) as raised:
        PyTorchFlightRecorderImporter().import_trace(
            trace_dir=FIXTURES / "unsupported",
            case_id="CASE-UNSUPPORTED",
            store=LocalEvidenceStore(store_root),
            captured_at=CAPTURED_AT,
        )
    assert raised.value.code is ImportErrorCode.UNSUPPORTED_VERSION
    assert "99.0" in str(raised.value)
    assert len(list(store_root.glob("cases/CASE-UNSUPPORTED/objects/sha256/*"))) == 2


def test_malformed_json_is_hashed_before_parse(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    (trace / "metadata.json").write_bytes(b"{not-json")
    store_root = tmp_path / "store"
    with pytest.raises(FlightRecorderImportError) as raised:
        PyTorchFlightRecorderImporter().import_trace(
            trace_dir=trace,
            case_id="CASE-MALFORMED",
            store=LocalEvidenceStore(store_root),
            captured_at=CAPTURED_AT,
        )
    assert raised.value.code is ImportErrorCode.MALFORMED_EVIDENCE
    assert len(list(store_root.glob("cases/CASE-MALFORMED/objects/sha256/*"))) == 1


def test_missing_rank_is_reported_without_inference(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    for name in ("metadata.json", "rank-0.json"):
        (trace / name).write_bytes((FIXTURES / "supported" / name).read_bytes())
    result = PyTorchFlightRecorderImporter().import_trace(
        trace_dir=trace,
        case_id="CASE-MISSING",
        store=LocalEvidenceStore(tmp_path / "store"),
        captured_at=CAPTURED_AT,
    )
    assert result.missing_ranks == [1]
    assert result.warnings == ["missing expected ranks: [1]"]
    assert result.native_findings[0].limitations == [
        "One or more expected rank files are missing."
    ]


def test_symlinked_trace_content_is_policy_blocked(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("{}", encoding="utf-8")
    (trace / "metadata.json").symlink_to(target)
    with pytest.raises(FlightRecorderImportError) as raised:
        PyTorchFlightRecorderImporter().import_trace(
            trace_dir=trace,
            case_id="CASE-MALICIOUS",
            store=LocalEvidenceStore(tmp_path / "store"),
            captured_at=CAPTURED_AT,
        )
    assert raised.value.code is ImportErrorCode.POLICY_BLOCKED
