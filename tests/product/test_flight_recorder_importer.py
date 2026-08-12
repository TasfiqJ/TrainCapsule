from __future__ import annotations

import json
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
    assert result.document_unknown_fields == {"rank-0.json": {}, "rank-1.json": {}}
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
    assert len(raised.value.raw_digests) == 2
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


def test_malformed_field_error_retains_every_raw_digest(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    for name in ("metadata.json", "rank-0.json", "rank-1.json"):
        (trace / name).write_bytes((FIXTURES / "supported" / name).read_bytes())
    metadata = json.loads((trace / "metadata.json").read_bytes())
    metadata["worldSize"] = "not-an-integer"
    (trace / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(FlightRecorderImportError) as raised:
        PyTorchFlightRecorderImporter().import_trace(
            trace_dir=trace,
            case_id="CASE-MALFORMED-FIELD",
            store=LocalEvidenceStore(tmp_path / "store"),
            captured_at=CAPTURED_AT,
        )
    assert raised.value.code is ImportErrorCode.MALFORMED_EVIDENCE
    assert set(raised.value.raw_digests) == {"metadata.json", "rank-0.json", "rank-1.json"}


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
    assert result.warnings == ["expected rank files not captured: [1]"]
    assert any("incomplete" in item for item in result.native_findings[0].limitations)
    assert "complete" not in result.native_findings[0].customer_decision_contribution.lower()


def test_public_real_format_shape_is_parsed_without_laundering_unknowns(
    tmp_path: Path,
) -> None:
    result = PyTorchFlightRecorderImporter().import_trace(
        trace_dir=FIXTURES / "real-format",
        case_id="CASE-REAL",
        store=LocalEvidenceStore(tmp_path / "store"),
        captured_at=CAPTURED_AT,
    )
    assert result.source_format == "pytorch-flight-recorder-json"
    assert result.source_format_version == "2.5"
    assert result.missing_ranks == []
    assert result.entries[0].collective_type == "nccl:all_reduce"
    assert result.entries[0].tensor_metadata == {
        "input_sizes": [[4096]],
        "input_dtypes": ["Float"],
    }
    assert result.entries[0].unknown_fields == {"record_id": 1001}


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
