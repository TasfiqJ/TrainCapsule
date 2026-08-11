from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import urlparse

CANONICAL_VERDICT_RE = re.compile(
    r"^\*\*Overall verdict:\s*(clear|conflicts_found|unknown)\*\*$",
    re.IGNORECASE | re.MULTILINE,
)
FINDING_ROW_RE = re.compile(
    r"^\|\s*\*\*([A-Z][A-Z0-9]*-\d+)\*\*\s*\|.*\|\s*"
    r"\*\*(CLEAR|CONFLICT|UNKNOWN)\*\*\s*\|\s*$",
    re.IGNORECASE | re.MULTILINE,
)
EVIDENCE_KINDS = {"target", "positive_control", "negative_control", "limitation"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ResearchPolicyError(ValueError):
    pass


def parse_research_record(record: str) -> tuple[str, dict[str, str]]:
    verdicts = [value.lower() for value in CANONICAL_VERDICT_RE.findall(record)]
    if len(verdicts) != 1:
        raise ResearchPolicyError(
            "research record must contain exactly one canonical '**Overall verdict: ...**' line"
        )
    labels: dict[str, str] = {}
    for finding_id, label in FINDING_ROW_RE.findall(record):
        normalized_id = finding_id.upper()
        if normalized_id in labels:
            raise ResearchPolicyError(f"duplicate findings-table ID: {normalized_id}")
        labels[normalized_id] = label.upper()
    if not labels:
        raise ResearchPolicyError(
            "research record must contain a markdown findings table with labeled IDs"
        )
    return verdicts[0], labels


def validate_verdict_consistency(record: str) -> list[str]:
    try:
        verdict, labels = parse_research_record(record)
    except ResearchPolicyError as exc:
        return [str(exc)]
    values = set(labels.values())
    if "CONFLICT" in values:
        expected = "conflicts_found"
    elif "UNKNOWN" in values:
        expected = "unknown"
    else:
        expected = "clear"
    if verdict != expected:
        return [
            f"overall verdict {verdict!r} contradicts itemized findings; expected {expected!r}"
        ]
    return []


def _allowed_host(source: str, allowed_domains: set[str]) -> bool:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return True
    host = (parsed.hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _artifact_path(repo_root: Path, manifest_path: Path, raw: str) -> Path:
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResearchPolicyError(f"unsafe evidence artifact path: {raw}")
    normalized = relative.as_posix().lstrip("./")
    evidence_root = manifest_path.parent.relative_to(repo_root).as_posix().rstrip("/")
    required_prefix = f"{evidence_root}/raw/"
    if not normalized.startswith(required_prefix):
        raise ResearchPolicyError(
            f"evidence artifact must stay under {required_prefix}: {normalized}"
        )
    return repo_root / normalized


def validate_evidence_manifest(
    *,
    repo_root: Path,
    manifest_path: Path,
    labels: dict[str, str],
    allowed_domains: set[str],
) -> list[str]:
    if not manifest_path.is_file():
        return [f"missing research evidence manifest: {manifest_path.relative_to(repo_root)}"]
    try:
        payload = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"invalid research evidence manifest: {exc}"]
    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("research evidence manifest version must be 1")
    if payload.get("task_id") != "T002":
        errors.append("research evidence manifest task_id must be T002")
    raw_entries_value = payload.get("evidence")
    if not isinstance(raw_entries_value, list) or not raw_entries_value:
        return [*errors, "research evidence manifest must contain evidence entries"]
    raw_entries = cast(list[object], raw_entries_value)

    seen_artifacts: set[str] = set()
    coverage: dict[str, dict[str, set[str]]] = {
        finding_id: {kind: set() for kind in EVIDENCE_KINDS} for finding_id in labels
    }
    required = {
        "finding_id",
        "kind",
        "query_shape",
        "source",
        "retrieved_at",
        "command",
        "artifact_path",
        "sha256",
        "outcome",
    }
    for index, raw_entry in enumerate(raw_entries, start=1):
        if not isinstance(raw_entry, dict):
            errors.append(f"evidence entry {index} must be an object")
            continue
        entry = cast(dict[str, Any], raw_entry)
        missing = sorted(required - set(entry))
        if missing:
            errors.append(f"evidence entry {index} is missing: {', '.join(missing)}")
            continue
        finding_id = str(entry["finding_id"]).upper()
        kind = str(entry["kind"]).lower()
        query_shape = str(entry["query_shape"]).strip()
        source = str(entry["source"]).strip()
        artifact_raw = str(entry["artifact_path"]).replace("\\", "/")
        digest = str(entry["sha256"]).lower()
        if finding_id not in labels:
            errors.append(f"evidence entry {index} references unknown finding {finding_id}")
            continue
        if kind not in EVIDENCE_KINDS:
            errors.append(f"evidence entry {index} has invalid kind {kind!r}")
            continue
        if not query_shape:
            errors.append(f"evidence entry {index} has an empty query_shape")
        if not source or not _allowed_host(source, allowed_domains):
            errors.append(f"evidence entry {index} uses a source outside the allowlist: {source}")
        try:
            timestamp = datetime.fromisoformat(str(entry["retrieved_at"]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timezone is missing")
        except ValueError:
            errors.append(f"evidence entry {index} has an invalid UTC/offset timestamp")
        if not str(entry["command"]).strip():
            errors.append(f"evidence entry {index} has an empty reproduction command")
        if not str(entry["outcome"]).strip():
            errors.append(f"evidence entry {index} has an empty outcome")
        if artifact_raw in seen_artifacts:
            errors.append(f"evidence artifact is reused by multiple entries: {artifact_raw}")
        seen_artifacts.add(artifact_raw)
        try:
            artifact = _artifact_path(repo_root, manifest_path, artifact_raw)
        except (ResearchPolicyError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if not artifact.is_file():
            errors.append(f"missing raw research artifact: {artifact_raw}")
        elif not SHA256_RE.fullmatch(digest):
            errors.append(f"evidence entry {index} has an invalid sha256")
        else:
            observed = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if observed != digest:
                errors.append(
                    f"evidence artifact hash mismatch for {artifact_raw}: {observed} != {digest}"
                )
        coverage[finding_id][kind].add(query_shape)

    for finding_id, label in labels.items():
        kinds = coverage[finding_id]
        if label == "CLEAR":
            if not kinds["target"]:
                errors.append(f"CLEAR finding {finding_id} has no raw target evidence")
            missing_controls = kinds["target"] - kinds["positive_control"]
            if missing_controls:
                errors.append(
                    f"CLEAR finding {finding_id} lacks same-shape positive controls for: "
                    + ", ".join(sorted(missing_controls))
                )
        elif not (kinds["target"] or kinds["limitation"]):
            errors.append(f"{label} finding {finding_id} has no target/limitation evidence")
    return errors
