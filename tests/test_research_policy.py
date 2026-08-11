from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tcfactory.research_policy import (
    parse_research_record,
    validate_evidence_manifest,
    validate_verdict_consistency,
)


def _record(label: str, verdict: str, *, prose: str = "") -> str:
    return (
        "# Research\n\n"
        "| ID | Check | Label |\n"
        "|---|---|---|\n"
        f"| **T-1** | target | **{label}** |\n\n"
        f"{prose}\n\n"
        f"**Overall verdict: {verdict}**\n"
    )


def _entry(
    *, finding_id: str, kind: str, query_shape: str, artifact_path: str, data: bytes
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "kind": kind,
        "query_shape": query_shape,
        "source": "https://tmsearch.uspto.gov/search",
        "retrieved_at": "2026-08-11T04:00:00Z",
        "command": "curl --fail --silent https://tmsearch.uspto.gov/search",
        "artifact_path": artifact_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "outcome": "controlled result",
    }


def _write_v2_bundle(
    tmp_path: Path,
    *,
    task_id: str = "T003",
    candidate_sha: str = "a" * 40,
    required_controls: list[str] | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    evidence_root = tmp_path / f"docs/evidence/{task_id}"
    raw_root = evidence_root / "raw"
    raw_root.mkdir(parents=True)
    endpoint = "https://docs.example.com/search"
    query_plan: dict[str, Any] = {
        "version": 2,
        "task_id": task_id,
        "candidate_sha": candidate_sha,
        "created_at": "2026-08-11T03:00:00Z",
        "findings": [
            {
                "finding_id": "T-1",
                "subject": "Example product identifier",
                "claim_boundary": "Exact-match result in the declared official index",
                "falsification_condition": "A controlled exact-match conflict is returned",
                "queries": [
                    {
                        "query_id": "T-1-primary",
                        "source_scheme": "https",
                        "source_class": "official_documentation",
                        "adapter": "http-json-v1",
                        "endpoint": endpoint,
                        "request_shape": "exact-term-json",
                        "freshness_days": 30,
                        "depends_on": [],
                        "required_controls": required_controls or ["negative_control"],
                    }
                ],
            }
        ],
    }
    plan_path = evidence_root / "query-plan.json"
    plan_path.write_text(json.dumps(query_plan, sort_keys=True), encoding="utf-8")

    evidence: list[dict[str, object]] = []
    for execution_id, kind, data in (
        ("exec-target", "target", b'{"hits": 0}\n'),
        ("exec-positive", "positive_control", b'{"hits": 1}\n'),
        ("exec-negative", "negative_control", b'{"rejected": true}\n'),
    ):
        artifact_path = f"docs/evidence/{task_id}/raw/{execution_id}.json"
        (raw_root / f"{execution_id}.json").write_bytes(data)
        evidence.append(
            {
                "execution_id": execution_id,
                "finding_id": "T-1",
                "query_id": "T-1-primary",
                "kind": kind,
                "source": endpoint,
                "source_scheme": "https",
                "source_class": "official_documentation",
                "adapter": "http-json-v1",
                "endpoint": endpoint,
                "request_shape": "exact-term-json",
                "retrieved_at": "2026-08-11T04:00:00Z",
                "response_status": "HTTP 200",
                "command": "research-adapter http-json-v1 --query T-1-primary",
                "artifact_path": artifact_path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "outcome": "controlled result",
            }
        )
    manifest: dict[str, Any] = {
        "version": 2,
        "task_id": task_id,
        "candidate_sha": candidate_sha,
        "query_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "evidence": evidence,
    }
    manifest_path = evidence_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path, plan_path, manifest, query_plan


def test_verdict_is_computed_from_itemized_findings_not_prose() -> None:
    honest = _record(
        "UNKNOWN",
        "unknown",
        prose="No UNKNOWN finding was converted to CLEAR in this record.",
    )
    assert validate_verdict_consistency(honest) == []

    false_clear = _record("CONFLICT", "clear")
    errors = validate_verdict_consistency(false_clear)
    assert errors and "expected 'conflicts_found'" in errors[0]


def test_research_record_requires_one_canonical_verdict_and_stable_findings() -> None:
    verdict, labels = parse_research_record(_record("CLEAR", "clear"))
    assert verdict == "clear"
    assert labels == {"T-1": "CLEAR"}


def test_evidence_manifest_recomputes_hashes_and_requires_same_shape_controls(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "docs/evidence/T002"
    raw_root = evidence_root / "raw"
    raw_root.mkdir(parents=True)
    target_data = b'{"hits": 0}\n'
    control_data = b'{"hits": 1}\n'
    target = raw_root / "target.json"
    control = raw_root / "control.json"
    target.write_bytes(target_data)
    control.write_bytes(control_data)
    manifest_path = evidence_root / "manifest.json"
    payload = {
        "version": 1,
        "task_id": "T002",
        "evidence": [
            _entry(
                finding_id="T-1",
                kind="target",
                query_shape="term.wordmarkExact",
                artifact_path="docs/evidence/T002/raw/target.json",
                data=target_data,
            ),
            _entry(
                finding_id="T-1",
                kind="positive_control",
                query_shape="term.wordmarkExact",
                artifact_path="docs/evidence/T002/raw/control.json",
                data=control_data,
            ),
        ],
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"uspto.gov"},
    )
    assert errors == []

    control.write_bytes(b"tampered\n")
    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"uspto.gov"},
    )
    assert any("hash mismatch" in error for error in errors)

    strict_errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"uspto.gov"},
        task_id="T002",
        require_version=2,
    )
    assert any("version must be 2" in error for error in strict_errors)


def test_clear_finding_rejects_a_different_shape_positive_control(tmp_path: Path) -> None:
    evidence_root = tmp_path / "docs/evidence/T002"
    raw_root = evidence_root / "raw"
    raw_root.mkdir(parents=True)
    target_data = b"target\n"
    control_data = b"control\n"
    (raw_root / "target.txt").write_bytes(target_data)
    (raw_root / "control.txt").write_bytes(control_data)
    manifest_path = evidence_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "task_id": "T002",
                "evidence": [
                    _entry(
                        finding_id="T-1",
                        kind="target",
                        query_shape="bool.must",
                        artifact_path="docs/evidence/T002/raw/target.txt",
                        data=target_data,
                    ),
                    _entry(
                        finding_id="T-1",
                        kind="positive_control",
                        query_shape="single.match",
                        artifact_path="docs/evidence/T002/raw/control.txt",
                        data=control_data,
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"uspto.gov"},
    )
    assert any("same-shape positive controls" in error for error in errors)


def test_v2_manifest_is_generic_and_bound_to_preregistered_query_plan(
    tmp_path: Path,
) -> None:
    manifest_path, plan_path, _manifest, _plan = _write_v2_bundle(tmp_path)

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )

    assert errors == []


def test_v2_query_plan_requires_an_acyclic_dependency_graph(tmp_path: Path) -> None:
    manifest_path, plan_path, manifest, plan = _write_v2_bundle(tmp_path)
    finding = cast(list[dict[str, Any]], plan["findings"])[0]
    primary = cast(list[dict[str, Any]], finding["queries"])[0]
    primary["depends_on"] = ["T-1-secondary"]
    secondary = dict(primary)
    secondary["query_id"] = "T-1-secondary"
    secondary["depends_on"] = ["T-1-primary"]
    finding["queries"] = [primary, secondary]
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    manifest["query_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )

    assert any("query dependency graph contains a cycle" in error for error in errors)


def test_v2_query_plan_accepts_a_valid_dependency_chain(tmp_path: Path) -> None:
    manifest_path, plan_path, manifest, plan = _write_v2_bundle(tmp_path)
    finding = cast(list[dict[str, Any]], plan["findings"])[0]
    primary = cast(list[dict[str, Any]], finding["queries"])[0]
    secondary = dict(primary)
    secondary["query_id"] = "T-1-secondary"
    secondary["depends_on"] = ["T-1-primary"]
    finding["queries"] = [primary, secondary]

    evidence = cast(list[dict[str, Any]], manifest["evidence"])
    for original in list(evidence):
        clone = dict(original)
        clone["execution_id"] = f"{original['execution_id']}-secondary"
        clone["query_id"] = "T-1-secondary"
        original_path = tmp_path / str(original["artifact_path"])
        clone_path = original_path.with_name(f"{original_path.stem}-secondary.json")
        clone_path.write_bytes(original_path.read_bytes())
        clone["artifact_path"] = clone_path.relative_to(tmp_path).as_posix()
        evidence.append(clone)

    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    manifest["query_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )

    assert errors == []


def test_v2_query_plan_rejects_missing_and_unknown_dependencies(tmp_path: Path) -> None:
    manifest_path, plan_path, manifest, plan = _write_v2_bundle(tmp_path)
    query = cast(list[dict[str, Any]], cast(list[dict[str, Any]], plan["findings"])[0]["queries"])[
        0
    ]
    query.pop("depends_on")
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    manifest["query_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    missing_errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )
    assert any("must declare depends_on" in error for error in missing_errors)

    query["depends_on"] = ["not-preregistered"]
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    manifest["query_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    unknown_errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )
    assert any("unknown query 'not-preregistered'" in error for error in unknown_errors)


def test_v2_manifest_rejects_omitted_expected_findings_and_wrong_task(
    tmp_path: Path,
) -> None:
    manifest_path, plan_path, manifest, plan = _write_v2_bundle(tmp_path)
    findings = cast(list[dict[str, Any]], plan["findings"])
    second = dict(findings[0])
    second["finding_id"] = "T-2"
    queries = cast(list[dict[str, Any]], second["queries"])
    second_query = dict(queries[0])
    second_query["query_id"] = "T-2-primary"
    second["queries"] = [second_query]
    findings.append(second)
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    manifest["query_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T004",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )

    assert any("task_id must be T004" in error for error in errors)
    assert any("missing=['T-2']" in error for error in errors)


def test_v2_manifest_binds_controls_to_query_and_requires_declared_negative_control(
    tmp_path: Path,
) -> None:
    manifest_path, plan_path, manifest, _plan = _write_v2_bundle(tmp_path)
    evidence = cast(list[dict[str, Any]], manifest["evidence"])
    evidence[:] = [entry for entry in evidence if entry["kind"] != "negative_control"]
    positive = next(entry for entry in evidence if entry["kind"] == "positive_control")
    positive["adapter"] = "different-adapter"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )

    assert any("adapter differs from preregistered query" in error for error in errors)
    assert any("lacks required controls: negative_control" in error for error in errors)


def test_v2_manifest_rejects_stale_future_and_non_authoritative_sources(
    tmp_path: Path,
) -> None:
    manifest_path, plan_path, manifest, _plan = _write_v2_bundle(tmp_path)
    evidence = cast(list[dict[str, Any]], manifest["evidence"])
    evidence[0]["retrieved_at"] = "2025-01-01T00:00:00Z"
    evidence[1]["retrieved_at"] = "2026-08-12T00:00:00Z"
    evidence[2]["source"] = "http://docs.example.com/search"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    errors = validate_evidence_manifest(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        labels={"T-1": "CLEAR"},
        allowed_domains={"example.com"},
        task_id="T003",
        query_plan_path=plan_path,
        require_version=2,
        now=datetime(2026, 8, 11, 5, tzinfo=UTC),
    )

    assert any("is stale" in error for error in errors)
    assert any("retrieved_at is in the future" in error for error in errors)
    assert any("source_scheme 'https' does not match source 'http'" in error for error in errors)
