from __future__ import annotations

import hashlib
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
from tcfactory.v3.source_authority import SourceAuthorityError

ROOT = Path(__file__).resolve().parents[1]


def repository_fixture(tmp_path: Path) -> Path:
    shutil.copytree(
        ROOT / "docs/source-of-truth",
        tmp_path / "docs/source-of-truth",
    )
    shutil.copytree(
        ROOT / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
        tmp_path / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
    )
    shutil.copy2(ROOT / "docs/CONTEXT_INDEX.yaml", tmp_path / "docs/CONTEXT_INDEX.yaml")
    shutil.copy2(ROOT / "SOURCE_PRECEDENCE.md", tmp_path / "SOURCE_PRECEDENCE.md")
    (tmp_path / "config").mkdir()
    (tmp_path / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/generate_v3_1_zh_source.py",
        tmp_path / "scripts/generate_v3_1_zh_source.py",
    )
    shutil.copy2(ROOT / "config/active_generation.yaml", tmp_path / "config/active_generation.yaml")
    shutil.copy2(ROOT / "config/context.yaml", tmp_path / "config/context.yaml")
    shutil.copy2(ROOT / "config/source_precedence.yaml", tmp_path / "config/source_precedence.yaml")
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
    path = repo / "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _rebind_manifest(repo: Path, manifest: Path) -> None:
    config_path = repo / "config/active_generation.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["manifestSha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def test_repository_v3_source_authority_is_integral() -> None:
    validate_repository(ROOT)


def test_integrity_rejects_missing_active_file(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    target = repo / (
        "docs/source-of-truth/v3.1-zh-2026-08-12/"
        "00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md"
    )
    target.unlink()
    with pytest.raises((OSError, SourceAuthorityError)):
        validate_repository(repo)


def test_integrity_rejects_changed_hash(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/source-of-truth/v3.1-zh-2026-08-12/00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md"
    path.write_text(path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    with pytest.raises(SourceAuthorityError, match="deterministic historical derivation"):
        validate_repository(repo)


def test_integrity_rejects_duplicate_logical_id(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path, payload = _manifest(repo)
    files = cast(list[dict[str, object]], payload["documents"])
    assert isinstance(files[0], dict) and isinstance(files[1], dict)
    files[1]["logicalId"] = files[0]["logicalId"]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _rebind_manifest(repo, path)
    with pytest.raises(SourceAuthorityError, match="deterministic historical derivation"):
        validate_repository(repo)


def test_integrity_rejects_manifest_self_hash(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path, payload = _manifest(repo)
    files = cast(list[dict[str, object]], payload["documents"])
    files.append(
        {
            "path": "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json",
            "logicalId": "TC.V3_1_ZH.SELF",
            "sha256": "0" * 64,
            "authorityClass": "metadata",
            "sections": [{"heading": "self", "level": 1, "sectionId": "self"}],
            "generationId": "traincapsule-v3.1-zh-2026-08-12",
            "derivedFrom": "TC.V3.SELF",
            "required": True,
        }
    )
    cast(dict[str, object], payload["integrity"])["documentCount"] = len(files)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _rebind_manifest(repo, path)
    with pytest.raises(SourceAuthorityError, match="deterministic historical derivation"):
        validate_repository(repo)


def test_integrity_rejects_active_parenthesized_duplicate(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    duplicate = repo / (
        "docs/source-of-truth/v3.1-zh-2026-08-12/"
        "00_EXECUTIVE_BUILD_DECISION_V3_1_ZH(1).md"
    )
    duplicate.write_text("duplicate\n", encoding="utf-8")
    with pytest.raises(SourceAuthorityError, match="membership mismatch"):
        validate_repository(repo)


def test_integrity_rejects_old_bundle_as_active(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "config/active_generation.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["sourceRoot"] = "docs/source-of-truth/v3-2026-08-11"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_repository(repo)


def test_integrity_rejects_unresolved_context_path(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["groups"]["product_normative"]["entries"][0]["path"] = "docs/missing.md"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="unresolved V3 context path"):
        validate_repository(repo)


def test_integrity_rejects_mixed_normative_and_current_fact_context(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
    path = repo / "docs/CONTEXT_INDEX.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["groups"]["current_facts"]["entries"][0]["authorityClass"] = "normative_product"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(SourceIntegrityError, match="current factual authority is mixed"):
        validate_repository(repo)


def test_integrity_rejects_synthetic_commercial_completion(tmp_path: Path) -> None:
    repo = repository_fixture(tmp_path)
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
