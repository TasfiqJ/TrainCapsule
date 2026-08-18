"""Deterministic, fail-closed re-verification for V3-MIG-001.

This module does not recreate a historical controller receipt.  It binds the
tracked historical records that remain available and states that authority
boundary explicitly.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

WORK_ITEM_ID = "V3-MIG-001"
EVIDENCE_PATH = Path(
    "docs/migrations/evidence/v3.1-zh/V3-MIG-001-reverification.json"
)
SCHEMA_PATH = Path("schemas/migrations/v3-mig-001-reverification.schema.json")
COMPONENTS = {
    "PHASE_0_BASELINE": Path("docs/migrations/V3_1_ZH_PHASE_0_BASELINE.json"),
    "BASELINE_REPORT": Path("docs/migrations/V3_BASELINE_REPORT.md"),
    "RUNTIME_SNAPSHOT": Path("docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json"),
}

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class Mig001ReverificationError(RuntimeError):
    """The historical V3-MIG-001 evidence cannot be verified exactly."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _read_required(repo_root: Path, relative: Path) -> bytes:
    path = repo_root / relative
    if not path.is_file():
        raise Mig001ReverificationError(f"required component is missing: {relative}")
    return path.read_bytes()


def _load_json(data: bytes, relative: Path) -> JsonObject:
    try:
        value = cast(JsonValue, json.loads(data))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Mig001ReverificationError(f"invalid JSON component: {relative}") from exc
    if not isinstance(value, dict):
        raise Mig001ReverificationError(f"component must be a JSON object: {relative}")
    return cast(JsonObject, value)


def _require_object(value: JsonValue, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise Mig001ReverificationError(f"{field} must be a JSON object")
    return value


def _require_string_list(value: JsonValue, field: str) -> list[str]:
    if not isinstance(value, list):
        raise Mig001ReverificationError(f"{field} must be a string array")
    items = cast(list[JsonValue], value)
    if not all(isinstance(item, str) for item in items):
        raise Mig001ReverificationError(f"{field} must be a string array")
    return cast(list[str], items)


def _require_object_list(value: JsonValue, field: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise Mig001ReverificationError(f"{field} must be an object array")
    objects: list[JsonObject] = []
    for item in cast(list[JsonValue], value):
        objects.append(_require_object(item, field))
    return objects


def _require_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise Mig001ReverificationError(f"{field} is not an exact Git SHA")
    return value


def _report_migration_base(report: str) -> str:
    match = re.search(r"^- Actual migration base: `([0-9a-f]{40})`$", report, re.MULTILINE)
    if match is None:
        raise Mig001ReverificationError("baseline report lacks the exact migration base")
    if "- Tracked worktree changes before migration: none" not in report:
        raise Mig001ReverificationError("baseline report lacks the clean tracked-worktree claim")
    return match.group(1)


def build_reverification(repo_root: Path) -> dict[str, Any]:
    """Build the canonical task-bound record from tracked historical inputs."""

    component_bytes = {
        role: _read_required(repo_root, path) for role, path in COMPONENTS.items()
    }
    phase0 = _load_json(component_bytes["PHASE_0_BASELINE"], COMPONENTS["PHASE_0_BASELINE"])
    runtime = _load_json(component_bytes["RUNTIME_SNAPSHOT"], COMPONENTS["RUNTIME_SNAPSHOT"])
    try:
        report = component_bytes["BASELINE_REPORT"].decode("utf-8")
        starting = _require_object(phase0["startingState"], "startingState")
        phase0_runtime = _require_object(phase0["runtime"], "runtime")
        runtime_queue = _require_object(runtime["queue"], "queue")
    except (UnicodeDecodeError, KeyError, TypeError) as exc:
        raise Mig001ReverificationError("historical baseline structure is incomplete") from exc

    phase0_local = _require_sha(starting.get("startingLocalHead"), "startingLocalHead")
    phase0_origin = _require_sha(starting.get("startingOriginMain"), "startingOriginMain")
    migration_base = _require_sha(runtime.get("head"), "runtime snapshot head")
    report_base = _report_migration_base(report)
    tracked_dirty = starting.get("trackedDirtyPaths")
    clean_claim = (
        phase0_local == phase0_origin
        and starting.get("ahead") == 0
        and starting.get("behind") == 0
        and starting.get("diverged") is False
        and tracked_dirty == []
    )
    if not clean_claim:
        raise Mig001ReverificationError("Phase-0 clean-status claim is not internally consistent")
    if migration_base != report_base:
        raise Mig001ReverificationError(
            "runtime snapshot head does not match the baseline report migration base"
        )

    queue_paths = _require_string_list(
        phase0_runtime.get("v2QueueArtifacts"), "Phase-0 queue inventory"
    )
    checkpoints = _require_string_list(
        phase0_runtime.get("v3Checkpoints"), "Phase-0 checkpoint inventory"
    )
    snapshot_files = _require_object_list(
        runtime_queue.get("files"), "runtime queue file inventory"
    )
    snapshot_paths = [
        str(item.get("path"))
        if str(item.get("path")).startswith("factory/queue/")
        else f"factory/queue/{item.get('path')}"
        for item in snapshot_files
    ]
    if sorted(queue_paths) != sorted(snapshot_paths):
        raise Mig001ReverificationError(
            "Phase-0 and runtime-snapshot queue inventories do not agree"
        )

    body: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceType": "TRACKED_HISTORICAL_REVERIFICATION",
        "workItemId": WORK_ITEM_ID,
        "componentBindings": [
            {
                "role": role,
                "path": str(COMPONENTS[role]),
                "bytes": len(component_bytes[role]),
                "sha256": _sha256(component_bytes[role]),
            }
            for role in sorted(COMPONENTS)
        ],
        "claims": {
            "migrationBaselineSha": migration_base,
            "phase0StartingSha": phase0_local,
            "cleanTrackedStatus": True,
            "cleanStatusBasis": {
                "startingLocalHeadEqualsOriginMain": True,
                "ahead": 0,
                "behind": 0,
                "diverged": False,
                "trackedDirtyPaths": [],
            },
            "queueInventory": {
                "phase0Paths": sorted(queue_paths),
                "snapshotSummary": runtime_queue.get("summary"),
                "snapshotFiles": sorted(snapshot_files, key=lambda item: str(item.get("path"))),
            },
            "checkpointInventory": sorted(checkpoints),
        },
        "authorityBoundary": {
            "authoritativeCompletionReceipt": False,
            "independentAuthorityPresent": False,
            "historicalFactsReverifiedFromTrackedArtifacts": True,
            "limitation": (
                "This deterministic record re-verifies tracked historical artifacts; "
                "it is not an original controller receipt or independent authority signature."
            ),
        },
    }
    body["evidenceDigest"] = _sha256(_canonical_bytes(body))
    return body


def validate_reverification(repo_root: Path) -> dict[str, Any]:
    """Validate schema, component hashes, semantic claims, and canonical digest."""

    schema = _load_json(_read_required(repo_root, SCHEMA_PATH), SCHEMA_PATH)
    evidence = cast(
        dict[str, Any],
        _load_json(_read_required(repo_root, EVIDENCE_PATH), EVIDENCE_PATH),
    )
    raw_errors = Draft202012Validator(schema).iter_errors(evidence)  # pyright: ignore[reportUnknownMemberType]
    errors: list[ValidationError] = sorted(raw_errors, key=lambda error: list(error.path))
    if errors:
        raise Mig001ReverificationError(f"schema validation failed: {errors[0].message}")
    expected = build_reverification(repo_root)
    if evidence != expected:
        raise Mig001ReverificationError(
            "checked-in V3-MIG-001 re-verification does not match its bound components"
        )
    return evidence


def render_reverification(repo_root: Path) -> bytes:
    """Return byte-stable JSON suitable for the checked-in evidence artifact."""

    return json.dumps(build_reverification(repo_root), indent=2, sort_keys=True).encode() + b"\n"
