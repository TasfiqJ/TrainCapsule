from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tcfactory.v3.mig_001_reverification import (
    COMPONENTS,
    EVIDENCE_PATH,
    SCHEMA_PATH,
    Mig001ReverificationError,
    build_reverification,
    render_reverification,
    validate_reverification,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_fixture(tmp_path: Path) -> Path:
    for relative in (*COMPONENTS.values(), SCHEMA_PATH, EVIDENCE_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path


def test_v3_mig_001_reverification_is_exact_and_deterministic() -> None:
    first = build_reverification(ROOT)
    second = build_reverification(ROOT)
    assert first == second
    assert render_reverification(ROOT) == render_reverification(ROOT)
    assert validate_reverification(ROOT) == first
    assert first["authorityBoundary"]["authoritativeCompletionReceipt"] is False
    assert first["authorityBoundary"]["independentAuthorityPresent"] is False


@pytest.mark.parametrize("role", sorted(COMPONENTS))
def test_v3_mig_001_reverification_rejects_missing_components(
    tmp_path: Path, role: str
) -> None:
    repo = _copy_fixture(tmp_path)
    (repo / COMPONENTS[role]).unlink()
    with pytest.raises(Mig001ReverificationError, match="required component is missing"):
        validate_reverification(repo)


@pytest.mark.parametrize("role", sorted(COMPONENTS))
def test_v3_mig_001_reverification_rejects_tampered_components(
    tmp_path: Path, role: str
) -> None:
    repo = _copy_fixture(tmp_path)
    path = repo / COMPONENTS[role]
    path.write_bytes(path.read_bytes() + b"\nTAMPERED\n")
    with pytest.raises(Mig001ReverificationError):
        validate_reverification(repo)


def test_v3_mig_001_reverification_rejects_missing_binding(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    evidence_path = repo / EVIDENCE_PATH
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["componentBindings"].pop()
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(Mig001ReverificationError, match="schema validation failed"):
        validate_reverification(repo)


def test_v3_mig_001_reverification_rejects_digest_tamper(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    evidence_path = repo / EVIDENCE_PATH
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["evidenceDigest"] = "sha256:" + "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(Mig001ReverificationError, match="does not match"):
        validate_reverification(repo)
