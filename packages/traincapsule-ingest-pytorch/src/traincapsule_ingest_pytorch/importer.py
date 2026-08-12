"""Bounded importer for controlled and public PyTorch Flight Recorder JSON shapes."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

from pydantic import Field
from traincapsule_core.base import ProductModel, digest_json, sha256_digest
from traincapsule_core.evidence import LocalEvidenceStore
from traincapsule_core.models import (
    EvidenceArtifact,
    FindingAttribution,
    NativeConfidence,
    NativeFinding,
)


class ImportErrorCode(StrEnum):
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    MALFORMED_EVIDENCE = "MALFORMED_EVIDENCE"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class FlightRecorderImportError(ValueError):
    def __init__(
        self, code: ImportErrorCode, message: str, *, raw_digests: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.raw_digests = raw_digests or {}


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
    source_format: str
    source_format_version: str
    pytorch_version: str
    world_size: int | None = Field(default=None, ge=1)
    artifacts: list[EvidenceArtifact] = Field(min_length=1)
    binding_artifacts: list[EvidenceArtifact] = []
    entries: list[FlightRecorderEntry]
    native_findings: list[NativeFinding]
    warnings: list[str]
    missing_ranks: list[int]
    raw_digests: dict[str, str]
    metadata_unknown_fields: dict[str, object]
    document_unknown_fields: dict[str, dict[str, object]]


class EvidenceImporter(Protocol):
    def import_trace(
        self,
        *,
        trace_dir: Path,
        case_id: str,
        store: LocalEvidenceStore,
        captured_at: datetime,
        workload_id: str | None = None,
        baseline_environment_id: str | None = None,
        candidate_environment_id: str | None = None,
    ) -> FlightRecorderImport: ...


LifecycleEntry = tuple[int, str, int, str, str]


def _bounded_json_object(
    payload: bytes, label: str, digests: dict[str, str], *, max_depth: int = 64
) -> dict[str, object]:
    depth = 0
    in_string = False
    escaped = False
    for value in payload:
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:
                escaped = True
            elif value == 0x22:
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value in (0x5B, 0x7B):
            depth += 1
            if depth > max_depth:
                raise FlightRecorderImportError(
                    ImportErrorCode.POLICY_BLOCKED,
                    f"{label} exceeds JSON nesting policy",
                    raw_digests=digests,
                )
        elif value in (0x5D, 0x7D):
            depth -= 1
    try:
        raw: object = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE,
            f"{label} is not valid bounded UTF-8 JSON",
            raw_digests=digests,
        ) from error
    if not isinstance(raw, dict):
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE,
            f"{label} must be a JSON object",
            raw_digests=digests,
        )
    return cast(dict[str, object], raw)


def verified_lifecycle_entries(
    artifacts: list[EvidenceArtifact],
    artifact_reader: Callable[[EvidenceArtifact], bytes],
) -> list[LifecycleEntry]:
    """Reparse lifecycle truth from raw CAS bytes, never from a caller's import record."""
    entries: list[LifecycleEntry] = []
    observed_ranks: set[int] = set()
    for artifact in artifacts:
        if (
            artifact.kind != "PYTORCH_FLIGHT_RECORDER_RAW"
            or artifact.source_adapter != "pytorch-flight-recorder"
        ):
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                "native baseline references a non-Flight-Recorder raw artifact",
            )
        payload = artifact_reader(artifact)
        if sha256_digest(payload) != artifact.content_digest:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                "raw lifecycle artifact digest mismatch",
                raw_digests={artifact.artifact_id: sha256_digest(payload)},
            )
        document = _bounded_json_object(
            payload,
            "raw lifecycle artifact",
            {artifact.artifact_id: artifact.content_digest},
        )
        raw_entries = document.get("entries")
        if raw_entries is None:
            continue
        if not isinstance(raw_entries, list):
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                "raw lifecycle entries must be a list",
                raw_digests={artifact.artifact_id: artifact.content_digest},
            )
        rank = document.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 0:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                "raw lifecycle rank must be a non-negative integer",
                raw_digests={artifact.artifact_id: artifact.content_digest},
            )
        if rank in observed_ranks:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"duplicate raw lifecycle rank {rank}",
                raw_digests={artifact.artifact_id: artifact.content_digest},
            )
        observed_ranks.add(rank)
        process_group = str(document.get("processGroup", document.get("pg_id", "UNKNOWN")))
        for index, raw_entry in enumerate(cast(list[object], raw_entries)):
            if not isinstance(raw_entry, dict):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"raw lifecycle entry {index} must be an object",
                    raw_digests={artifact.artifact_id: artifact.content_digest},
                )
            entry = cast(dict[str, object], raw_entry)
            sequence = entry.get("sequenceId", entry.get("collective_seq_id"))
            collective = entry.get("collectiveType", entry.get("profiling_name"))
            state = entry.get("state")
            if (
                not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or sequence < 0
                or not isinstance(collective, str)
                or not collective
                or not isinstance(state, str)
                or not state
            ):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"raw lifecycle entry {index} has invalid identity/state fields",
                    raw_digests={artifact.artifact_id: artifact.content_digest},
                )
            entries.append((rank, process_group, sequence, collective, state))
    if not entries:
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE,
            "native baseline has no raw lifecycle entries",
        )
    return entries


def lifecycle_disagreement_from_raw(
    artifacts: list[EvidenceArtifact],
    artifact_reader: Callable[[EvidenceArtifact], bytes],
) -> bool:
    entries = verified_lifecycle_entries(artifacts, artifact_reader)
    observed_ranks: set[int] = set()
    for artifact in artifacts:
        payload = artifact_reader(artifact)
        document = _bounded_json_object(
            payload, "raw lifecycle artifact", {artifact.artifact_id: artifact.content_digest}
        )
        if document.get("entries") is not None:
            rank = document.get("rank")
            if isinstance(rank, int) and not isinstance(rank, bool) and rank >= 0:
                observed_ranks.add(rank)
    states: dict[tuple[str, int, str], dict[int, str]] = {}
    for rank, process_group, sequence, collective, state in entries:
        states.setdefault((process_group, sequence, collective), {})[rank] = state.casefold()
    return any(
        len(set(rank_states.values())) > 1 or set(rank_states) != observed_ranks
        for rank_states in states.values()
    )


def verify_import_against_raw(
    imported: FlightRecorderImport,
    artifact_reader: Callable[[EvidenceArtifact], bytes],
) -> bool:
    raw_entries = Counter(verified_lifecycle_entries(imported.artifacts, artifact_reader))
    claimed_entries = Counter(
        (
            entry.rank,
            entry.process_group,
            entry.sequence_id,
            entry.collective_type,
            entry.state,
        )
        for entry in imported.entries
    )
    if raw_entries != claimed_entries:
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE,
            "Flight Recorder import lifecycle entries do not match raw CAS evidence",
            raw_digests=imported.raw_digests,
        )
    expected_digests = {
        artifact.provenance.get("sourceRelativePath", artifact.artifact_id): (
            artifact.content_digest
        )
        for artifact in imported.artifacts
    }
    if imported.raw_digests != expected_digests:
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE,
            "Flight Recorder import raw digest map does not match its artifacts",
            raw_digests=expected_digests,
        )
    return lifecycle_disagreement_from_raw(imported.artifacts, artifact_reader)


class PyTorchFlightRecorderImporter:
    CONTROLLED_FORMAT = "pytorch-flight-recorder"
    REAL_FORMAT = "pytorch-flight-recorder-json"
    SUPPORTED_VERSIONS = frozenset({"1.0", "2.5"})

    def __init__(self, *, max_files: int = 1024, max_total_bytes: int = 64 * 1024 * 1024):
        if max_files < 1 or max_total_bytes < 1:
            raise ValueError("import limits must be positive")
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes

    @staticmethod
    def _object(payload: bytes, label: str, digests: dict[str, str]) -> dict[str, object]:
        return _bounded_json_object(payload, label, digests)

    @staticmethod
    def _integer(value: object, label: str, digests: dict[str, str]) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"{label} must be a non-negative integer",
                raw_digests=digests,
            )
        return value

    @staticmethod
    def _string(value: object, label: str, digests: dict[str, str]) -> str:
        if not isinstance(value, str) or not value:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE,
                f"{label} must be a non-empty string",
                raw_digests=digests,
            )
        return value

    @staticmethod
    def _read_regular_file(path: Path, *, limit: int) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            stat = os.fstat(fd)
            if stat.st_size > limit:
                raise FlightRecorderImportError(
                    ImportErrorCode.POLICY_BLOCKED, "trace file exceeds remaining size policy"
                )
            payload = bytearray()
            while True:
                chunk = os.read(fd, min(1024 * 1024, limit + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > limit:
                    raise FlightRecorderImportError(
                        ImportErrorCode.POLICY_BLOCKED, "trace size exceeds policy"
                    )
            return bytes(payload)
        finally:
            os.close(fd)

    def import_trace(
        self,
        *,
        trace_dir: Path,
        case_id: str,
        store: LocalEvidenceStore,
        captured_at: datetime,
        workload_id: str | None = None,
        baseline_environment_id: str | None = None,
        candidate_environment_id: str | None = None,
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
        if len(paths) > self.max_files:
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED, "trace file count exceeds policy"
            )
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise FlightRecorderImportError(
                ImportErrorCode.POLICY_BLOCKED, "trace directory may contain regular files only"
            )
        artifacts: list[EvidenceArtifact] = []
        payloads: dict[str, bytes] = {}
        digests: dict[str, str] = {}
        remaining = self.max_total_bytes
        for path in paths:
            relative = path.relative_to(root).as_posix()
            payload = self._read_regular_file(path, limit=remaining)
            remaining -= len(payload)
            artifact = store.put_bytes(
                case_id=case_id,
                payload=payload,
                kind="PYTORCH_FLIGHT_RECORDER_RAW",
                source_adapter="pytorch-flight-recorder",
                source_version="RAW_UNPARSED",
                captured_at=captured_at,
                provenance={"sourceRelativePath": relative},
                workload_id=workload_id,
                baseline_environment_id=baseline_environment_id,
                candidate_environment_id=candidate_environment_id,
            )
            artifacts.append(artifact)
            payloads[relative] = payload
            digests[relative] = artifact.content_digest
        if not paths:
            raise FlightRecorderImportError(
                ImportErrorCode.MALFORMED_EVIDENCE, "trace directory is empty", raw_digests=digests
            )

        metadata_unknown: dict[str, object] = {}
        document_unknown: dict[str, dict[str, object]] = {}
        expected_ranks: list[int] | None = None
        if "metadata.json" in payloads:
            metadata = self._object(payloads["metadata.json"], "metadata.json", digests)
            source_format = self._string(metadata.get("format"), "metadata.json.format", digests)
            version = self._string(
                metadata.get("schemaVersion"), "metadata.json.schemaVersion", digests
            )
            pytorch_version = self._string(
                metadata.get("pytorchVersion"), "metadata.json.pytorchVersion", digests
            )
            world_size = self._integer(
                metadata.get("worldSize"), "metadata.json.worldSize", digests
            )
            raw_expected = metadata.get("expectedRanks")
            if not isinstance(raw_expected, list):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    "metadata.json.expectedRanks must be a list",
                    raw_digests=digests,
                )
            expected_ranks = [
                self._integer(value, "metadata.json.expectedRanks[]", digests)
                for value in cast(list[object], raw_expected)
            ]
            if sorted(expected_ranks) != list(range(world_size)):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    "expectedRanks must enumerate worldSize exactly once",
                    raw_digests=digests,
                )
            known = {"format", "schemaVersion", "pytorchVersion", "worldSize", "expectedRanks"}
            metadata_unknown = {key: value for key, value in metadata.items() if key not in known}
            document_names = [name for name in payloads if name != "metadata.json"]
        else:
            first_name = sorted(payloads)[0]
            first = self._object(payloads[first_name], first_name, digests)
            source_format = self.REAL_FORMAT
            version = self._string(first.get("version"), f"{first_name}.version", digests)
            pytorch_version = self._string(
                first.get("pytorch_version"), f"{first_name}.pytorch_version", digests
            )
            raw_world = first.get("world_size")
            world_size = (
                self._integer(raw_world, f"{first_name}.world_size", digests)
                if raw_world is not None
                else None
            )
            expected_ranks = list(range(world_size)) if world_size is not None else None
            document_names = sorted(payloads)
        if (
            source_format not in {self.CONTROLLED_FORMAT, self.REAL_FORMAT}
            or version not in self.SUPPORTED_VERSIONS
        ):
            raise FlightRecorderImportError(
                ImportErrorCode.UNSUPPORTED_VERSION,
                f"unsupported Flight Recorder format/version: {source_format}/{version}",
                raw_digests=digests,
            )

        entries: list[FlightRecorderEntry] = []
        observed: set[int] = set()
        warnings: list[str] = []
        for name in document_names:
            document = self._object(payloads[name], name, digests)
            if source_format == self.REAL_FORMAT:
                document_version = self._string(
                    document.get("version"), f"{name}.version", digests
                )
                document_pytorch = self._string(
                    document.get("pytorch_version"), f"{name}.pytorch_version", digests
                )
                raw_document_world = document.get("world_size")
                document_world = (
                    self._integer(raw_document_world, f"{name}.world_size", digests)
                    if raw_document_world is not None
                    else None
                )
                if (
                    document_version != version
                    or document_pytorch != pytorch_version
                    or document_world != world_size
                ):
                    raise FlightRecorderImportError(
                        ImportErrorCode.MALFORMED_EVIDENCE,
                        f"{name} conflicts with the trace version/runtime/world-size identity",
                        raw_digests=digests,
                    )
            rank = self._integer(document.get("rank"), f"{name}.rank", digests)
            if world_size is not None and rank >= world_size:
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"{name}.rank is outside worldSize",
                    raw_digests=digests,
                )
            if rank in observed:
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"duplicate rank {rank}",
                    raw_digests=digests,
                )
            observed.add(rank)
            process_group = str(document.get("processGroup", document.get("pg_id", "UNKNOWN")))
            raw_entries = document.get("entries")
            if not isinstance(raw_entries, list):
                raise FlightRecorderImportError(
                    ImportErrorCode.MALFORMED_EVIDENCE,
                    f"{name}.entries must be a list",
                    raw_digests=digests,
                )
            root_known = {
                "rank",
                "processGroup",
                "pg_id",
                "entries",
                "version",
                "pytorch_version",
                "world_size",
                "pg_config",
            }
            document_unknown[name] = {
                key: value for key, value in document.items() if key not in root_known
            }
            for index, raw_entry in enumerate(cast(list[object], raw_entries)):
                if not isinstance(raw_entry, dict):
                    raise FlightRecorderImportError(
                        ImportErrorCode.MALFORMED_EVIDENCE,
                        f"{name}.entries[{index}] must be an object",
                        raw_digests=digests,
                    )
                entry = cast(dict[str, object], raw_entry)
                sequence = entry.get("sequenceId", entry.get("collective_seq_id"))
                collective = entry.get("collectiveType", entry.get("profiling_name"))
                state = entry.get("state")
                tensor = entry.get("tensorMetadata")
                if tensor is None:
                    tensor = {
                        key: entry[key]
                        for key in ("input_sizes", "output_sizes", "input_dtypes", "output_dtypes")
                        if key in entry
                    } or None
                stack_raw = entry.get("callStack", entry.get("frames", []))
                if not isinstance(stack_raw, list):
                    raise FlightRecorderImportError(
                        ImportErrorCode.MALFORMED_EVIDENCE,
                        f"{name}.entries[{index}] stack must be a list",
                        raw_digests=digests,
                    )
                stack: list[str] = [
                    value if isinstance(value, str) else json.dumps(value, sort_keys=True)
                    for value in cast(list[object], stack_raw)
                ]
                known = {
                    "sequenceId",
                    "collective_seq_id",
                    "collectiveType",
                    "profiling_name",
                    "state",
                    "tensorMetadata",
                    "input_sizes",
                    "output_sizes",
                    "input_dtypes",
                    "output_dtypes",
                    "callStack",
                    "frames",
                }
                entries.append(
                    FlightRecorderEntry(
                        rank=rank,
                        process_group=process_group,
                        sequence_id=self._integer(
                            sequence, f"{name}.entries[{index}].sequence", digests
                        ),
                        collective_type=self._string(
                            collective, f"{name}.entries[{index}].collective", digests
                        ),
                        state=self._string(state, f"{name}.entries[{index}].state", digests),
                        tensor_metadata=cast(dict[str, object] | None, tensor),
                        call_stack=stack,
                        unknown_fields={
                            key: value for key, value in entry.items() if key not in known
                        },
                    )
                )
        missing = sorted(set(expected_ranks or []) - observed)
        if missing:
            warnings.append(f"expected rank files not captured: {missing}")
        if expected_ranks is None:
            warnings.append("expected rank set was not declared; missing ranks are UNKNOWN")
        observation = (
            f"Flight Recorder directly reported {len(entries)} lifecycle entries across "
            f"{len(observed)} observed ranks."
        )
        limitations = ["Importer reports native observations; it does not infer root cause."]
        if missing:
            limitations.append(f"Evidence is incomplete because ranks {missing} were not captured.")
        if expected_ranks is None:
            limitations.append(
                "Completeness across ranks is unknown without a declared world size."
            )
        finding_payload: dict[str, object] = {
            "schemaVersion": 1,
            "attribution": FindingAttribution.NATIVE_TOOL_FOUND.value,
            "nativeSystem": "PyTorch Flight Recorder",
            "nativeVersion": pytorch_version,
            "observation": observation,
            "evidenceRefs": sorted(digests.values()),
            "confidenceClass": NativeConfidence.DIRECT_OBSERVATION.value,
            "limitations": limitations,
            "customerDecisionContribution": (
                "Preserves native observations and explicit evidence limits."
            ),
        }
        finding_payload["findingId"] = digest_json(finding_payload)
        finding = NativeFinding.model_validate(finding_payload)
        return FlightRecorderImport(
            case_id=case_id,
            source_format=source_format,
            source_format_version=version,
            pytorch_version=pytorch_version,
            world_size=world_size,
            artifacts=artifacts,
            entries=entries,
            native_findings=[finding],
            warnings=warnings,
            missing_ranks=missing,
            raw_digests=digests,
            metadata_unknown_fields=metadata_unknown,
            document_unknown_fields=document_unknown,
        )


def reimport_from_raw_artifacts(
    artifacts: list[EvidenceArtifact],
    artifact_reader: Callable[[EvidenceArtifact], bytes],
    *,
    binding_artifacts: list[EvidenceArtifact] | None = None,
) -> FlightRecorderImport:
    """Reconstruct the complete importer record from authenticated raw artifacts."""
    if not artifacts:
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE, "native import has no raw artifacts"
        )
    first = artifacts[0]
    bindings = (
        first.case_id,
        first.workload_id,
        first.baseline_environment_id,
        first.candidate_environment_id,
        first.captured_at,
    )
    if any(
        (
            item.case_id,
            item.workload_id,
            item.baseline_environment_id,
            item.candidate_environment_id,
            item.captured_at,
        )
        != bindings
        for item in artifacts
    ):
        raise FlightRecorderImportError(
            ImportErrorCode.MALFORMED_EVIDENCE,
            "raw artifacts do not share exact case, identity, and capture bindings",
        )
    with tempfile.TemporaryDirectory(prefix="traincapsule-reimport-") as temporary:
        root = Path(temporary)
        trace = root / "trace"
        trace.mkdir()
        for artifact in artifacts:
            relative = artifact.provenance.get("sourceRelativePath")
            if relative is None or Path(relative).name != relative or relative in {".", ".."}:
                raise FlightRecorderImportError(
                    ImportErrorCode.POLICY_BLOCKED,
                    "raw artifact sourceRelativePath is unsafe",
                )
            path = trace / relative
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(artifact_reader(artifact))
        imported = PyTorchFlightRecorderImporter().import_trace(
            trace_dir=trace,
            case_id=first.case_id,
            store=LocalEvidenceStore(root / "store"),
            captured_at=first.captured_at,
            workload_id=first.workload_id,
            baseline_environment_id=first.baseline_environment_id,
            candidate_environment_id=first.candidate_environment_id,
        )
        return imported.model_copy(update={"binding_artifacts": binding_artifacts or []})
