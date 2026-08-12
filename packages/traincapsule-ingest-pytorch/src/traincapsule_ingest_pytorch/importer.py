"""Bounded PyTorch Flight Recorder importer for controlled/public fixtures."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

from pydantic import Field
from traincapsule_core.base import ProductModel, digest_json
from traincapsule_core.evidence import LocalEvidenceStore
from traincapsule_core.models import EvidenceArtifact, NativeConfidence, NativeFinding


class ImportErrorCode(StrEnum):
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    MALFORMED_EVIDENCE = "MALFORMED_EVIDENCE"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class FlightRecorderImportError(ValueError):
    def __init__(self, code: ImportErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class FlightRecorderEntry(ProductModel):
    rank: int = Field(ge=0)
    process_group: str = Field(min_length=1)
    sequence_id: int = Field(ge=0)
    collective_type: str = Field(min_length=1)
    state: str = Field(min_length=1)
    tensor_metadata: dict[str, object] | None = None
    call_stack: list[str]
    unknown_fields: dict[str, object]


class FlightRecorderImport(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: str
    source_format_version: str
    pytorch_version: str
    world_size: int = Field(ge=1)
    artifacts: list[EvidenceArtifact]
    entries: list[FlightRecorderEntry]
    native_findings: list[NativeFinding]
    warnings: list[str]
    missing_ranks: list[int]
    raw_digests: dict[str, str]
    metadata_unknown_fields: dict[str, object]


class EvidenceImporter(Protocol):
    def import_trace(
        self,
        *,
        trace_dir: Path,
        case_id: str,
        store: LocalEvidenceStore,
        captured_at: datetime,
    ) -> FlightRecorderImport: ...


class PyTorchFlightRecorderImporter:
    SUPPORTED_FORMAT = "pytorch-flight-recorder"
    SUPPORTED_VERSIONS = frozenset({"1.0"})

    def __init__(self, *, max_files: int = 1024, max_total_bytes: int = 64 * 1024 * 1024):
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes

    @staticmethod
    def _object(payload: bytes, label: str) -> dict[str, object]:
        try:
            raw: object = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"{label} is not valid UTF-8 JSON",
            ) from error
        if not isinstance(raw, dict):
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"{label} must be a JSON object",
            )
        return cast(dict[str, object], raw)

    @staticmethod
    def _required_string(payload: dict[str, object], key: str, label: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"{label}.{key} must be a non-empty string",
            )
        return value

    @staticmethod
    def _required_int(payload: dict[str, object], key: str, label: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"{label}.{key} must be a non-negative integer",
            )
        return value

    def import_trace(
        self,
        *,
        trace_dir: Path,
        case_id: str,
        store: LocalEvidenceStore,
        captured_at: datetime,
    ) -> FlightRecorderImport:
        if trace_dir.is_symlink():
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED, "trace directory cannot be a symlink"
            )
        root = trace_dir.resolve(strict=True)
        if not root.is_dir():
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE, "trace path must be a directory"
            )
        paths = sorted(root.iterdir())
        if any(path.is_symlink() for path in paths):
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED, "trace directory contains a symlink"
            )
        if any(not path.is_file() for path in paths):
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED,
                "trace directory may contain regular files only",
            )
        if len(paths) > self.max_files:
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED, "trace file count exceeds policy"
            )
        if sum(path.stat().st_size for path in paths) > self.max_total_bytes:
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED, "trace size exceeds policy"
            )
        metadata_path = root / "metadata.json"
        if metadata_path not in paths:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE, "metadata.json is required"
            )

        artifacts: list[EvidenceArtifact] = []
        raw_payloads: dict[str, bytes] = {}
        raw_digests: dict[str, str] = {}
        for path in paths:
            relative = path.relative_to(root).as_posix()
            payload = path.read_bytes()
            artifact = store.put_bytes(
                case_id=case_id,
                payload=payload,
                kind=(
                    "PYTORCH_FLIGHT_RECORDER_METADATA"
                    if relative == "metadata.json"
                    else "PYTORCH_FLIGHT_RECORDER_RANK"
                ),
                source_adapter="pytorch-flight-recorder",
                source_version="unparsed",
                captured_at=captured_at,
                provenance={"sourceRelativePath": relative},
            )
            artifacts.append(artifact)
            raw_payloads[relative] = payload
            raw_digests[relative] = artifact.content_digest

        metadata = self._object(raw_payloads["metadata.json"], "metadata.json")
        source_format = self._required_string(metadata, "format", "metadata.json")
        version = self._required_string(metadata, "schemaVersion", "metadata.json")
        if source_format != self.SUPPORTED_FORMAT or version not in self.SUPPORTED_VERSIONS:
            raise FlightRecorderImportError(
                ImportErrorCode.UNSUPPORTED_VERSION,
                f"unsupported Flight Recorder format/version: {source_format}/{version}",
            )
        pytorch_version = self._required_string(
            metadata, "pytorchVersion", "metadata.json"
        )
        world_size = self._required_int(metadata, "worldSize", "metadata.json")
        if world_size < 1:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE, "worldSize must be positive"
            )
        expected_raw = metadata.get("expectedRanks")
        if not isinstance(expected_raw, list):
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                "metadata.json.expectedRanks must contain non-negative integers",
            )
        expected_ranks: list[int] = []
        for expected_rank in cast(list[object], expected_raw):
            if (
                not isinstance(expected_rank, int)
                or isinstance(expected_rank, bool)
                or expected_rank < 0
            ):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    "metadata.json.expectedRanks must contain non-negative integers",
                )
            expected_ranks.append(expected_rank)
        expected_ranks.sort()
        if expected_ranks != list(range(world_size)):
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                "expectedRanks must contain each rank in worldSize exactly once",
            )
        metadata_known = {
            "format",
            "schemaVersion",
            "pytorchVersion",
            "worldSize",
            "expectedRanks",
        }
        metadata_unknown = {
            key: value for key, value in metadata.items() if key not in metadata_known
        }

        entries: list[FlightRecorderEntry] = []
        observed_ranks: set[int] = set()
        warnings: list[str] = []
        for relative, payload in sorted(raw_payloads.items()):
            if relative == "metadata.json":
                continue
            document = self._object(payload, relative)
            rank = self._required_int(document, "rank", relative)
            if rank >= world_size:
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"{relative}.rank is outside worldSize",
                )
            if rank in observed_ranks:
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"duplicate Flight Recorder document for rank {rank}",
                )
            process_group = self._required_string(document, "processGroup", relative)
            observed_ranks.add(rank)
            raw_entries = document.get("entries")
            if not isinstance(raw_entries, list):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"{relative}.entries must be a list",
                )
            for index, raw_entry in enumerate(cast(list[object], raw_entries)):
                if not isinstance(raw_entry, dict):
                    raise FlightRecorderImportError(
                        ImportErrorCode.MALFORMED_EVIDENCE,
                        f"{relative}.entries[{index}] must be an object",
                    )
                entry = cast(dict[str, object], raw_entry)
                known = {
                    "sequenceId",
                    "collectiveType",
                    "state",
                    "tensorMetadata",
                    "callStack",
                }
                call_stack_raw = entry.get("callStack", [])
                if not isinstance(call_stack_raw, list):
                    raise FlightRecorderImportError(
                        ImportErrorCode.MALFORMED_EVIDENCE,
                        f"{relative}.entries[{index}].callStack must contain strings",
                    )
                call_stack: list[str] = []
                for raw_line in cast(list[object], call_stack_raw):
                    if not isinstance(raw_line, str):
                        raise FlightRecorderImportError(
                            ImportErrorCode.MALFORMED_EVIDENCE,
                            f"{relative}.entries[{index}].callStack must contain strings",
                        )
                    call_stack.append(raw_line)
                tensor_raw = entry.get("tensorMetadata")
                if tensor_raw is not None and not isinstance(tensor_raw, dict):
                    raise FlightRecorderImportError(
                        ImportErrorCode.MALFORMED_EVIDENCE,
                        f"{relative}.entries[{index}].tensorMetadata must be an object",
                    )
                entries.append(
                    FlightRecorderEntry(
                        rank=rank,
                        process_group=process_group,
                        sequence_id=self._required_int(
                            entry, "sequenceId", f"{relative}.entries[{index}]"
                        ),
                        collective_type=self._required_string(
                            entry, "collectiveType", f"{relative}.entries[{index}]"
                        ),
                        state=self._required_string(
                            entry, "state", f"{relative}.entries[{index}]"
                        ),
                        tensor_metadata=(
                            cast(dict[str, object], tensor_raw)
                            if isinstance(tensor_raw, dict)
                            else None
                        ),
                        call_stack=call_stack,
                        unknown_fields={
                            key: value for key, value in entry.items() if key not in known
                        },
                    )
                )
            document_unknown = set(document) - {"rank", "processGroup", "entries"}
            if document_unknown:
                warnings.append(
                    f"{relative} preserved unknown fields: {sorted(document_unknown)}"
                )

        missing = sorted(set(expected_ranks) - observed_ranks)
        if missing:
            warnings.append(f"missing expected ranks: {missing}")
        observation = (
            f"Flight Recorder directly reported {len(entries)} collective lifecycle "
            f"entries across {len(observed_ranks)} ranks; missing ranks={missing}."
        )
        finding = NativeFinding(
            finding_id=digest_json(
                {
                    "nativeSystem": "PyTorch Flight Recorder",
                    "nativeVersion": pytorch_version,
                    "observation": observation,
                    "evidenceRefs": sorted(raw_digests.values()),
                }
            ),
            native_system="PyTorch Flight Recorder",
            native_version=pytorch_version,
            observation=observation,
            evidence_refs=sorted(artifact.artifact_id for artifact in artifacts),
            confidence_class=NativeConfidence.DIRECT_OBSERVATION,
            limitations=(
                ["One or more expected rank files are missing."]
                if missing
                else ["Importer reports native observations; it does not infer root cause."]
            ),
            customer_decision_contribution="Preserves the complete native diagnostic baseline.",
        )
        return FlightRecorderImport(
            case_id=case_id,
            source_format_version=version,
            pytorch_version=pytorch_version,
            world_size=world_size,
            artifacts=artifacts,
            entries=entries,
            native_findings=[finding],
            warnings=warnings,
            missing_ranks=missing,
            raw_digests=raw_digests,
            metadata_unknown_fields=metadata_unknown,
        )
