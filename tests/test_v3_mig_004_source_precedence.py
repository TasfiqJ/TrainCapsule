from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import scripts.gates.source_of_truth_integrity as integrity
from scripts.gates.source_of_truth_integrity import SourceIntegrityError, validate_repository
from scripts.gates.v3_mig_004_evidence import OUTPUT, render
from tests.test_source_of_truth_integrity import repository_fixture


def _yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _rebind_policy(monkeypatch: pytest.MonkeyPatch, path: Path, payload: dict[str, Any]) -> None:
    digest = integrity.canonical_policy_digest(payload)
    payload["policyDigest"] = digest
    _write_yaml(path, payload)
    monkeypatch.setattr(integrity, "EXPECTED_PRECEDENCE_POLICY_DIGEST", digest)


def test_v3_mig_004_policy_is_machine_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    validate_repository(root)


def test_v3_mig_004_evidence_is_deterministic() -> None:
    assert OUTPUT.read_text(encoding="utf-8") == render()


def test_v3_mig_004_rejects_precedence_mutation_even_with_fresh_self_digest(
    tmp_path: Path,
) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "config/source_precedence.yaml"
    payload = _yaml(path)
    order = cast(list[str], payload["normativeOrder"])
    order[0], order[1] = order[1], order[0]
    payload["policyDigest"] = integrity.canonical_policy_digest(payload)
    _write_yaml(path, payload)
    with pytest.raises(SourceIntegrityError, match="not verifier-bound"):
        validate_repository(repo)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_v3_mig_004_rejects_missing_or_duplicate_precedence_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "config/source_precedence.yaml"
    payload = _yaml(path)
    order = cast(list[str], payload["normativeOrder"])
    if mutation == "missing":
        order.pop()
    else:
        order.append(order[0])
    _rebind_policy(monkeypatch, path, payload)
    expected = "canonical order" if mutation == "missing" else "duplicates"
    with pytest.raises(SourceIntegrityError, match=expected):
        integrity.validate_precedence_policy(repo)


def test_v3_mig_004_rejects_manifest_missing_precedence_source(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = cast(list[dict[str, Any]], payload["documents"])
    documents.pop(1)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="missing or duplicated"):
        integrity.validate_precedence_policy(repo)


def test_v3_mig_004_rejects_normative_source_in_current_fact_group(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = _yaml(path)
    payload["groups"]["current_facts"]["entries"][0]["authorityClass"] = "normative_product"
    _write_yaml(path, payload)
    with pytest.raises(SourceIntegrityError, match="mixed with normative authority"):
        validate_repository(repo)


def test_v3_mig_004_rejects_current_fact_in_normative_group(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = _yaml(path)
    payload["groups"]["product_normative"]["entries"][0]["authorityClass"] = "current_fact"
    payload["groups"]["product_normative"]["entries"][0]["freshnessPolicy"] = (
        "recheck_before_customer_claim"
    )
    _write_yaml(path, payload)
    with pytest.raises(SourceIntegrityError, match="normative group"):
        validate_repository(repo)


def test_v3_mig_004_rejects_role_group_authority_mismatch(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = _yaml(path)
    payload["groups"]["product_normative"]["includeRoles"].remove("builder")
    _write_yaml(path, payload)
    with pytest.raises(SourceIntegrityError, match="role/group authority mismatch"):
        validate_repository(repo)


def test_v3_mig_004_rejects_stale_current_fact(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = _yaml(path)
    payload["groups"]["current_facts"]["entries"][0]["freshnessStatus"] = "STALE"
    _write_yaml(path, payload)
    with pytest.raises(SourceIntegrityError, match="stale current fact"):
        validate_repository(repo)


def test_v3_mig_004_rejects_duplicate_context_entry(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = _yaml(path)
    entries = payload["groups"]["product_normative"]["entries"]
    entries[1] = dict(entries[0])
    _write_yaml(path, payload)
    with pytest.raises(SourceIntegrityError, match="duplicate context source"):
        validate_repository(repo)
