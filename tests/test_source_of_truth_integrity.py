from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import cast

import pytest
import yaml

from scripts.gates.source_of_truth_integrity import (
    SourceIntegrityError,
    validate_repository,
)

ROOT = Path(__file__).resolve().parents[1]


def _repository_fixture(tmp_path: Path) -> Path:
    shutil.copytree(
        ROOT / "docs/source-of-truth/v3-2026-08-11",
        tmp_path / "docs/source-of-truth/v3-2026-08-11",
    )
    shutil.copy2(ROOT / "docs/CONTEXT_INDEX.yaml", tmp_path / "docs/CONTEXT_INDEX.yaml")
    shutil.copy2(ROOT / "SOURCE_PRECEDENCE.md", tmp_path / "SOURCE_PRECEDENCE.md")
    (tmp_path / "config").mkdir()
    shutil.copy2(ROOT / "config/human_approval.yaml", tmp_path / "config/human_approval.yaml")
    shutil.copy2(ROOT / "config/owner_directives.yaml", tmp_path / "config/owner_directives.yaml")
    (tmp_path / "docs/migrations").mkdir(parents=True)
    shutil.copy2(
        ROOT / "docs/migrations/V3_OWNER_DIRECTIVES.md",
        tmp_path / "docs/migrations/V3_OWNER_DIRECTIVES.md",
    )
    for relative in (
        "SECURITY.md",
        "CLAUDE.md",
        "pyproject.toml",
        "prompts/research.md",
        "tcfactory/research_policy.py",
        "tcfactory/quality_policy.py",
        "scripts/gates/output_and_integration_gate.py",
        "scripts/gates/fast_quality.sh",
        "config/factory.yaml",
        "config/claude_features.yaml",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path


def _manifest(repo: Path) -> tuple[Path, dict[str, object]]:
    path = repo / "docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_repository_v3_source_authority_is_integral() -> None:
    validate_repository(ROOT)


def test_integrity_rejects_missing_active_file(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    (repo / "docs/source-of-truth/v3-2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md").unlink()
    with pytest.raises(SourceIntegrityError, match="membership mismatch"):
        validate_repository(repo)


def test_integrity_rejects_changed_hash(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path = repo / "docs/source-of-truth/v3-2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md"
    path.write_text(path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="manifest content or canonical hashes"):
        validate_repository(repo)


def test_integrity_rejects_duplicate_logical_id(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path, payload = _manifest(repo)
    files = cast(list[dict[str, object]], payload["files"])
    assert isinstance(files[0], dict) and isinstance(files[1], dict)
    files[1]["logicalId"] = files[0]["logicalId"]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="duplicate active logical ID"):
        validate_repository(repo)


def test_integrity_rejects_manifest_self_hash(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path, payload = _manifest(repo)
    files = cast(list[dict[str, object]], payload["files"])
    files.append(
        {
            "path": "FINAL_MANIFEST_V3.json",
            "logicalId": "final_manifest_v3",
            "sha256": "0" * 64,
            "bytes": 0,
            "authorityClass": "metadata",
        }
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="self-hash"):
        validate_repository(repo)


def test_integrity_rejects_active_parenthesized_duplicate(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    duplicate = repo / "docs/source-of-truth/v3-2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3(1).md"
    duplicate.write_text("duplicate\n", encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="membership mismatch"):
        validate_repository(repo)


def test_integrity_rejects_old_bundle_as_active(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path = repo / "SOURCE_PRECEDENCE.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "docs/source-of-truth/v3-2026-08-11/",
            "docs/source-of-truth/final-2026-08-09/",
        ),
        encoding="utf-8",
    )
    with pytest.raises(SourceIntegrityError, match="does not identify the active V3 bundle"):
        validate_repository(repo)


def test_integrity_rejects_unresolved_context_path(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["groups"]["product_normative"]["entries"][0]["path"] = "docs/missing.md"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="unresolved V3 context path"):
        validate_repository(repo)


def test_integrity_rejects_mixed_normative_and_current_fact_context(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["groups"]["current_facts"]["entries"][0]["authorityClass"] = "normative_product"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="current factual authority is mixed"):
        validate_repository(repo)


def test_integrity_rejects_synthetic_commercial_completion(tmp_path: Path) -> None:
    repo = _repository_fixture(tmp_path)
    path = repo / "factory/roadmap/milestones.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "milestones:\n"
        "  - milestoneId: M4_PAID_PILOT\n"
        "    type: COMMERCIAL\n"
        "    status: COMPLETED\n"
        "    syntheticTestOnly: true\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceIntegrityError, match="synthetic evidence"):
        validate_repository(repo)
