from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
