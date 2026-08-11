from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
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
EVIDENCE_KINDS = {
    "target",
    "positive_control",
    "negative_control",
    "error_control",
    "limitation",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
V2_SOURCE_SCHEMES = {"https", "git+https", "repo"}
V2_SOURCE_CLASSES = {
    "official_registry",
    "official_documentation",
    "standards_body",
    "versioned_repository",
    "peer_reviewed_publication",
    "first_party_api",
    "repository_source",
    "access_limitation",
}
V2_CONTROL_KINDS = {"positive_control", "negative_control", "error_control"}


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
    if parsed.scheme not in {"http", "https", "git+https"}:
        return True
    host = (parsed.hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _source_scheme(source: str) -> str:
    return urlparse(source).scheme.lower()


def _parse_timestamp(value: object, *, label: str, errors: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone is missing")
        return parsed.astimezone(UTC)
    except ValueError:
        errors.append(f"{label} has an invalid UTC/offset timestamp")
        return None


def _repo_source_path(repo_root: Path, source: str) -> Path | None:
    if not source.startswith("repo:"):
        return None
    raw = source.removeprefix("repo:").lstrip("/")
    relative = PurePosixPath(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        return None
    return repo_root / relative.as_posix()


def _validate_v2_source(
    *,
    repo_root: Path,
    source: str,
    source_scheme: str,
    source_class: str,
    allowed_domains: set[str],
    label: str,
) -> list[str]:
    errors: list[str] = []
    observed_scheme = _source_scheme(source)
    if source_scheme not in V2_SOURCE_SCHEMES:
        errors.append(f"{label} has unsupported source_scheme {source_scheme!r}")
    if observed_scheme != source_scheme:
        errors.append(
            f"{label} source_scheme {source_scheme!r} does not match source {observed_scheme!r}"
        )
    if source_class not in V2_SOURCE_CLASSES:
        errors.append(f"{label} has unsupported source_class {source_class!r}")
    if source_scheme in {"https", "git+https"}:
        if not _allowed_host(source, allowed_domains):
            errors.append(f"{label} uses a source outside the allowlist: {source}")
    elif source_scheme == "repo":
        path = _repo_source_path(repo_root, source)
        if path is None or not path.is_file():
            errors.append(f"{label} repository source is missing or unsafe: {source}")
        if source_class != "repository_source":
            errors.append(f"{label} repo source must use source_class='repository_source'")
    return errors


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
    task_id: str = "T002",
    query_plan_path: Path | None = None,
    current_candidate_sha: str | None = None,
    require_version: int | None = None,
    now: datetime | None = None,
) -> list[str]:
    if not manifest_path.is_file():
        return [f"missing research evidence manifest: {manifest_path.relative_to(repo_root)}"]
    try:
        raw_payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"invalid research evidence manifest: {exc}"]
    if not isinstance(raw_payload, dict):
        return ["research evidence manifest must be a JSON object"]
    payload = cast(dict[str, Any], raw_payload)
    errors: list[str] = []
    version = payload.get("version")
    if version not in {1, 2}:
        return ["research evidence manifest version must be 1 or 2"]
    if require_version is not None and version != require_version:
        errors.append(f"research evidence manifest version must be {require_version}")
    if payload.get("task_id") != task_id:
        errors.append(f"research evidence manifest task_id must be {task_id}")
    if version == 2:
        return [
            *errors,
            *_validate_v2_manifest(
                repo_root=repo_root,
                manifest_path=manifest_path,
                payload=payload,
                labels=labels,
                allowed_domains=allowed_domains,
                task_id=task_id,
                query_plan_path=query_plan_path,
                current_candidate_sha=current_candidate_sha,
                now=now,
            ),
        ]

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


def _validate_v2_manifest(
    *,
    repo_root: Path,
    manifest_path: Path,
    payload: dict[str, Any],
    labels: dict[str, str],
    allowed_domains: set[str],
    task_id: str,
    query_plan_path: Path | None,
    current_candidate_sha: str | None,
    now: datetime | None,
) -> list[str]:
    errors: list[str] = []
    candidate_sha = str(payload.get("candidate_sha") or "").lower()
    if not COMMIT_SHA_RE.fullmatch(candidate_sha):
        errors.append("research evidence manifest has an invalid candidate_sha")
    if current_candidate_sha and COMMIT_SHA_RE.fullmatch(candidate_sha):
        current = current_candidate_sha.lower()
        if candidate_sha != current:
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", candidate_sha, current],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            if ancestry.returncode != 0:
                errors.append(
                    "research evidence candidate_sha is not the reviewed candidate or an ancestor"
                )

    if query_plan_path is None:
        query_plan_path = manifest_path.parent / "query-plan.json"
    if not query_plan_path.is_file():
        return [*errors, f"missing preregistered research query plan: {query_plan_path}"]
    try:
        raw_plan: object = json.loads(query_plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [*errors, f"invalid research query plan: {exc}"]
    if not isinstance(raw_plan, dict):
        return [*errors, "research query plan must be a JSON object"]
    plan = cast(dict[str, Any], raw_plan)
    observed_plan_digest = hashlib.sha256(query_plan_path.read_bytes()).hexdigest()
    declared_plan_digest = str(payload.get("query_plan_sha256") or "").lower()
    if declared_plan_digest != observed_plan_digest:
        errors.append(
            "research query-plan digest mismatch: "
            f"{declared_plan_digest or '<missing>'} != {observed_plan_digest}"
        )
    if plan.get("version") != 2:
        errors.append("research query plan version must be 2")
    if plan.get("task_id") != task_id:
        errors.append(f"research query plan task_id must be {task_id}")
    if str(plan.get("candidate_sha") or "").lower() != candidate_sha:
        errors.append("research query plan and manifest candidate_sha differ")

    clock = (now or datetime.now(UTC)).astimezone(UTC)
    planned_at = _parse_timestamp(
        plan.get("created_at"), label="research query plan created_at", errors=errors
    )
    if planned_at and planned_at > clock + timedelta(minutes=5):
        errors.append("research query plan created_at is in the future")

    raw_findings = plan.get("findings")
    if not isinstance(raw_findings, list) or not raw_findings:
        return [*errors, "research query plan must contain expected findings"]

    planned_queries: dict[str, dict[str, Any]] = {}
    finding_queries: dict[str, list[str]] = {}
    for finding_index, raw_finding in enumerate(cast(list[object], raw_findings), start=1):
        if not isinstance(raw_finding, dict):
            errors.append(f"query-plan finding {finding_index} must be an object")
            continue
        finding = cast(dict[str, Any], raw_finding)
        finding_id = str(finding.get("finding_id") or "").upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]*-\d+", finding_id):
            errors.append(f"query-plan finding {finding_index} has an invalid finding_id")
            continue
        if finding_id in finding_queries:
            errors.append(f"duplicate query-plan finding_id: {finding_id}")
            continue
        for field in ("subject", "claim_boundary", "falsification_condition"):
            if not str(finding.get(field) or "").strip():
                errors.append(f"query-plan finding {finding_id} has an empty {field}")
        raw_queries = finding.get("queries")
        if not isinstance(raw_queries, list) or not raw_queries:
            errors.append(f"query-plan finding {finding_id} has no queries")
            finding_queries[finding_id] = []
            continue
        finding_queries[finding_id] = []
        for query_index, raw_query in enumerate(cast(list[object], raw_queries), start=1):
            if not isinstance(raw_query, dict):
                errors.append(
                    f"query-plan finding {finding_id} query {query_index} must be an object"
                )
                continue
            query = cast(dict[str, Any], raw_query)
            query_id = str(query.get("query_id") or "").strip()
            if not query_id or query_id in planned_queries:
                errors.append(f"duplicate or empty research query_id: {query_id!r}")
                continue
            required_controls_value = query.get("required_controls", [])
            required_controls: set[str] = (
                {str(value) for value in cast(list[object], required_controls_value)}
                if isinstance(required_controls_value, list)
                else set[str]()
            )
            invalid_controls = sorted(required_controls - V2_CONTROL_KINDS)
            if invalid_controls:
                errors.append(
                    f"query-plan query {query_id} has invalid required_controls: "
                    + ", ".join(invalid_controls)
                )
            freshness_days = query.get("freshness_days")
            if not isinstance(freshness_days, int) or not 1 <= freshness_days <= 3650:
                errors.append(f"query-plan query {query_id} has invalid freshness_days")
            for field in ("adapter", "endpoint", "request_shape"):
                if not str(query.get(field) or "").strip():
                    errors.append(f"query-plan query {query_id} has an empty {field}")
            source_scheme = str(query.get("source_scheme") or "").lower()
            source_class = str(query.get("source_class") or "").lower()
            endpoint = str(query.get("endpoint") or "").strip()
            errors.extend(
                _validate_v2_source(
                    repo_root=repo_root,
                    source=endpoint,
                    source_scheme=source_scheme,
                    source_class=source_class,
                    allowed_domains=allowed_domains,
                    label=f"query-plan query {query_id}",
                )
            )
            normalized = dict(query)
            normalized["finding_id"] = finding_id
            normalized["required_controls"] = required_controls
            planned_queries[query_id] = normalized
            finding_queries[finding_id].append(query_id)

    expected_findings = set(finding_queries)
    observed_findings = set(labels)
    if expected_findings != observed_findings:
        missing = sorted(expected_findings - observed_findings)
        unexpected = sorted(observed_findings - expected_findings)
        errors.append(
            f"research findings do not match preregistered coverage: missing={missing}, "
            f"unexpected={unexpected}"
        )

    raw_entries = payload.get("evidence")
    if not isinstance(raw_entries, list) or not raw_entries:
        return [*errors, "research evidence manifest must contain evidence entries"]
    required_entry_fields = {
        "execution_id",
        "finding_id",
        "query_id",
        "kind",
        "source",
        "source_scheme",
        "source_class",
        "adapter",
        "endpoint",
        "request_shape",
        "retrieved_at",
        "response_status",
        "command",
        "artifact_path",
        "sha256",
        "outcome",
    }
    seen_executions: set[str] = set()
    seen_artifacts: set[str] = set()
    coverage: dict[str, set[str]] = {query_id: set() for query_id in planned_queries}
    for index, raw_entry in enumerate(cast(list[object], raw_entries), start=1):
        if not isinstance(raw_entry, dict):
            errors.append(f"evidence entry {index} must be an object")
            continue
        entry = cast(dict[str, Any], raw_entry)
        missing_fields = sorted(required_entry_fields - set(entry))
        if missing_fields:
            errors.append(f"evidence entry {index} is missing: {', '.join(missing_fields)}")
            continue
        execution_id = str(entry["execution_id"]).strip()
        if not execution_id or execution_id in seen_executions:
            errors.append(f"duplicate or empty evidence execution_id: {execution_id!r}")
        seen_executions.add(execution_id)
        query_id = str(entry["query_id"]).strip()
        planned = planned_queries.get(query_id)
        if planned is None:
            errors.append(f"evidence entry {index} references unknown query {query_id!r}")
            continue
        finding_id = str(entry["finding_id"]).upper()
        if finding_id != planned["finding_id"]:
            errors.append(f"evidence entry {index} query/finding binding differs from plan")
        kind = str(entry["kind"]).lower()
        if kind not in EVIDENCE_KINDS:
            errors.append(f"evidence entry {index} has invalid kind {kind!r}")
            continue
        for field in ("source_scheme", "source_class", "adapter", "endpoint", "request_shape"):
            if str(entry[field]).strip() != str(planned.get(field) or "").strip():
                errors.append(
                    f"evidence entry {index} {field} differs from preregistered query {query_id}"
                )
        source = str(entry["source"]).strip()
        errors.extend(
            _validate_v2_source(
                repo_root=repo_root,
                source=source,
                source_scheme=str(entry["source_scheme"]).lower(),
                source_class=str(entry["source_class"]).lower(),
                allowed_domains=allowed_domains,
                label=f"evidence entry {index}",
            )
        )
        source_host = (urlparse(source).hostname or "").lower()
        endpoint_host = (urlparse(str(entry["endpoint"])).hostname or "").lower()
        if source_host and endpoint_host and source_host != endpoint_host:
            errors.append(f"evidence entry {index} source and endpoint hosts differ")
        retrieved_at = _parse_timestamp(
            entry["retrieved_at"], label=f"evidence entry {index} retrieved_at", errors=errors
        )
        if retrieved_at:
            if retrieved_at > clock + timedelta(minutes=5):
                errors.append(f"evidence entry {index} retrieved_at is in the future")
            freshness_days = planned.get("freshness_days")
            if isinstance(freshness_days, int) and retrieved_at < clock - timedelta(
                days=freshness_days
            ):
                errors.append(f"evidence entry {index} is stale for query {query_id}")
            if planned_at and retrieved_at < planned_at:
                errors.append(f"evidence entry {index} predates the preregistered query plan")
        for field in ("response_status", "command", "outcome"):
            if not str(entry[field]).strip():
                errors.append(f"evidence entry {index} has an empty {field}")
        artifact_raw = str(entry["artifact_path"]).replace("\\", "/")
        if artifact_raw in seen_artifacts:
            errors.append(f"evidence artifact is reused by multiple entries: {artifact_raw}")
        seen_artifacts.add(artifact_raw)
        try:
            artifact = _artifact_path(repo_root, manifest_path, artifact_raw)
        except (ResearchPolicyError, ValueError) as exc:
            errors.append(str(exc))
            continue
        digest = str(entry["sha256"]).lower()
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
        coverage[query_id].add(kind)

    for finding_id, query_ids in finding_queries.items():
        label = labels.get(finding_id)
        for query_id in query_ids:
            kinds = coverage.get(query_id, set())
            if not ({"target", "limitation"} & kinds):
                errors.append(f"query {query_id} has no target or limitation evidence")
            required_controls = set(planned_queries[query_id]["required_controls"])
            if label == "CLEAR":
                if "target" not in kinds:
                    errors.append(f"CLEAR finding {finding_id} query {query_id} has no target")
                required_controls.add("positive_control")
            missing_controls = sorted(required_controls - kinds)
            if missing_controls:
                errors.append(
                    f"query {query_id} lacks required controls: {', '.join(missing_controls)}"
                )
    return errors
