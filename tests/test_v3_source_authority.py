from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from scripts.generate_v3_1_zh_source import HERE as GENERATED_SOURCE_ROOT
from scripts.generate_v3_1_zh_source import MANIFEST_PATH as GENERATED_MANIFEST_PATH
from scripts.generate_v3_1_zh_source import build as build_v31_source
from scripts.generate_v3_1_zh_source import canonical_json
from scripts.generate_v3_1_zh_source import validate as validate_generated_v31_source
from tcfactory.v3.source_authority import (
    SourceAuthorityError,
    emit_stale_source_proposal,
    validate_active_source_generation,
)

GENERATION = "traincapsule-v3.1-zh-2026-08-12"
SOURCE_ROOT = "docs/source-of-truth/v3.1-zh-2026-08-12"
MANIFEST = f"{SOURCE_ROOT}/FINAL_MANIFEST_V3_1_ZH.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority_repo(tmp_path: Path) -> Path:
    source = tmp_path / SOURCE_ROOT
    source.mkdir(parents=True)
    historical = tmp_path / "docs/source-of-truth/v3-2026-08-11/00_AUTHORITY.md"
    historical.parent.mkdir(parents=True)
    historical.write_text("# Normative authority\n", encoding="utf-8")
    document = source / "00_AUTHORITY.md"
    document.write_text("# Normative authority\n", encoding="utf-8")
    coverage = source / "SECTION_COVERAGE_V3_TO_V3_1_ZH.json"
    coverage_payload = {
        "schemaVersion": 1,
        "generationId": GENERATION,
        "generatedAt": datetime(2026, 8, 12, tzinfo=UTC).isoformat(),
        "rule": "every source heading maps in order",
        "documents": [
            {
                "logicalId": "00_authority",
                "sourcePath": "docs/source-of-truth/v3-2026-08-11/00_AUTHORITY.md",
                "targetPath": f"{SOURCE_ROOT}/00_AUTHORITY.md",
                "sourceSha256": _digest(historical),
                "targetSha256": _digest(document),
                "sourceHeadingCount": 1,
                "mappedHeadingCount": 1,
                "mappings": [
                    {
                        "sourceHeading": "Normative authority",
                        "sourceLine": 1,
                        "targetHeading": "Normative authority",
                        "targetSectionId": "normative-authority",
                        "targetLine": 1,
                        "disposition": "PRESERVED",
                    }
                ],
            }
        ],
        "totals": {"sourceHeadingCount": 1, "mappedHeadingCount": 1},
    }
    coverage.write_text(json.dumps(coverage_payload), encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "generationId": GENERATION,
        "generatedAt": datetime(2026, 8, 12, tzinfo=UTC).isoformat(),
        "authorityModel": {"normative": "manifest_locked"},
        "supersession": {"supersedesGenerationId": "traincapsule-v3-2026-08-11"},
        "documents": [
            {
                "logicalId": "00_authority",
                "path": f"{SOURCE_ROOT}/00_AUTHORITY.md",
                "sha256": _digest(document),
                "authorityClass": "normative",
                "sections": [
                    {
                        "heading": "Normative authority",
                        "level": 1,
                        "sectionId": "normative-authority",
                    }
                ],
                "generationId": GENERATION,
                "derivedFrom": "TC.V3.AUTHORITY",
                "required": True,
            }
        ],
        "coverageEvidence": {
            "path": f"{SOURCE_ROOT}/SECTION_COVERAGE_V3_TO_V3_1_ZH.json",
            "sha256": _digest(coverage),
            "sourceHeadingCount": 1,
            "mappedHeadingCount": 1,
        },
        "integrity": {
            "algorithm": "sha256",
            "documentCount": 1,
            "generatorPath": "scripts/generate_v3_1_zh_source.py",
            "manifestSelfIncluded": False,
        },
    }
    manifest_path = tmp_path / MANIFEST
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    generator_path = tmp_path / "scripts/generate_v3_1_zh_source.py"
    generator_path.parent.mkdir(parents=True)
    generator_path.write_text(
        """from pathlib import Path
import sys

expected = b\"# Normative authority\\n\"
target = Path(__file__).resolve().parents[1] / (
    \"docs/source-of-truth/v3.1-zh-2026-08-12/00_AUTHORITY.md\"
)
raise SystemExit(0 if \"--check\" in sys.argv and target.read_bytes() == expected else 1)
""",
        encoding="utf-8",
    )
    config = {
        "schemaVersion": "3.1",
        "schemaId": "traincapsule.active-generation/v3.1-zh",
        "generationId": GENERATION,
        "sourceRoot": SOURCE_ROOT,
        "manifestPath": MANIFEST,
        "manifestSha256": _digest(manifest_path),
        "generatorPath": "scripts/generate_v3_1_zh_source.py",
        "generatorSha256": _digest(generator_path),
        "deterministicDerivationCheckRequired": True,
        "supersedesGenerationId": "traincapsule-v3-2026-08-11",
        "mixedNormativeGenerationPolicy": "REJECT",
    }
    config_path = tmp_path / "config/active_generation.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    context = {
        "version": 3,
        "activeBundle": SOURCE_ROOT,
        "groups": {
            "product_normative": {
                "authorityClass": "normative",
                "entries": [
                    {
                        "path": f"{SOURCE_ROOT}/00_AUTHORITY.md",
                        "authorityClass": "normative",
                        "authoritySections": ["§Normative authority"],
                    }
                ],
            }
        },
    }
    context_path = tmp_path / "docs/CONTEXT_INDEX.yaml"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(yaml.safe_dump(context, sort_keys=False), encoding="utf-8")
    return tmp_path


def test_active_generation_validates_manifest_documents_and_context(tmp_path: Path) -> None:
    root = _authority_repo(tmp_path)
    active = validate_active_source_generation(root)
    assert active.generation_id == GENERATION
    assert active.manifest_path == MANIFEST
    assert active.source_digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("target", "semantic", "label"),
    [
        (
            "README.md",
            "The repository owner's later zero-human directive replaces independent "
            "machine-policy authorization with candidate-bound deterministic "
            "machine-policy receipts.",
            "local receipts replacing independent machine authority",
        ),
        (
            "README.md",
            "`FINAL_MANIFEST_V3.json` is generated by `scripts/generate_v3_manifest.py`.",
            "stale active V3 manifest",
        ),
            (
                "FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md",
                "releaseMode: pull_request",
                "reachable pull-request doctrine",
            ),
    ],
)
def test_generator_rejects_hash_rebound_stale_doctrine(
    target: str, semantic: str, label: str
) -> None:
    outputs = build_v31_source()
    target_path = GENERATED_SOURCE_ROOT / target
    outputs[target_path] += f"\n{semantic}\n".encode()
    manifest = json.loads(outputs[GENERATED_MANIFEST_PATH])
    document = next(item for item in manifest["documents"] if item["path"].endswith(target))
    document["sha256"] = hashlib.sha256(outputs[target_path]).hexdigest()
    outputs[GENERATED_MANIFEST_PATH] = canonical_json(manifest)

    errors = validate_generated_v31_source(outputs)

    assert any(label in error for error in errors)


def test_generator_rejects_removed_independent_authority_doctrine() -> None:
    outputs = build_v31_source()
    target_path = GENERATED_SOURCE_ROOT / "README.md"
    required = "Independent machine-policy authorization remains mandatory"
    outputs[target_path] = outputs[target_path].replace(
        required.encode(), b"Local deterministic authorization is sufficient", 1
    )
    manifest = json.loads(outputs[GENERATED_MANIFEST_PATH])
    document = next(
        item for item in manifest["documents"] if item["path"].endswith("README.md")
    )
    document["sha256"] = hashlib.sha256(outputs[target_path]).hexdigest()
    outputs[GENERATED_MANIFEST_PATH] = canonical_json(manifest)

    errors = validate_generated_v31_source(outputs)

    assert any("missing target doctrine" in error and required in error for error in errors)


@pytest.mark.parametrize(
    "attack",
    [
        "document",
        "self_rebound_body",
        "manifest",
        "mixed_context",
        "mixed_current_fact",
        "mixed_executor_policy",
        "bad_authority_section",
        "undeclared_active_file",
        "nested_smuggling",
        "fake_coverage_counts",
        "missing",
    ],
)
def test_active_generation_fails_closed_on_source_attacks(
    tmp_path: Path, attack: str
) -> None:
    root = _authority_repo(tmp_path)
    if attack == "document":
        (root / SOURCE_ROOT / "00_AUTHORITY.md").write_text("tampered\n", encoding="utf-8")
    elif attack == "self_rebound_body":
        document = root / SOURCE_ROOT / "00_AUTHORITY.md"
        document.write_text("# Normative authority\nsemantic tamper\n", encoding="utf-8")
        coverage_path = root / SOURCE_ROOT / "SECTION_COVERAGE_V3_TO_V3_1_ZH.json"
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage["documents"][0]["targetSha256"] = _digest(document)
        coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
        manifest_path = root / MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["documents"][0]["sha256"] = _digest(document)
        manifest["coverageEvidence"]["sha256"] = _digest(coverage_path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        config_path = root / "config/active_generation.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["manifestSha256"] = _digest(manifest_path)
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    elif attack == "manifest":
        (root / MANIFEST).write_text("{}\n", encoding="utf-8")
    elif attack in {
        "mixed_context",
        "mixed_current_fact",
        "mixed_executor_policy",
        "bad_authority_section",
    }:
        context_path = root / "docs/CONTEXT_INDEX.yaml"
        context = yaml.safe_load(context_path.read_text(encoding="utf-8"))
        entry = context["groups"]["product_normative"]["entries"][0]
        if attack == "bad_authority_section":
            entry["authoritySections"] = ["§00.2 truncated shadow heading"]
        else:
            entry["path"] = (
                "docs/source-of-truth/v3-2026-08-11/00_OLD.md"
            )
            if attack == "mixed_current_fact":
                entry["authorityClass"] = "current_fact"
            elif attack == "mixed_executor_policy":
                entry["authorityClass"] = "executor_policy"
        context_path.write_text(yaml.safe_dump(context), encoding="utf-8")
    elif attack == "undeclared_active_file":
        (root / SOURCE_ROOT / "SHADOW.md").write_text("shadow\n", encoding="utf-8")
    elif attack == "nested_smuggling":
        shadow = root / SOURCE_ROOT / "shadow"
        shadow.mkdir()
        (shadow / "SHADOW.md").write_text("shadow\n", encoding="utf-8")
    elif attack == "fake_coverage_counts":
        coverage_path = root / SOURCE_ROOT / "SECTION_COVERAGE_V3_TO_V3_1_ZH.json"
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage["totals"]["sourceHeadingCount"] = 99
        coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
        manifest_path = root / MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["coverageEvidence"]["sha256"] = _digest(coverage_path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        config_path = root / "config/active_generation.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["manifestSha256"] = _digest(manifest_path)
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    else:
        (root / SOURCE_ROOT / "00_AUTHORITY.md").unlink()
    with pytest.raises((OSError, ValueError, SourceAuthorityError)):
        validate_active_source_generation(root)


def test_stale_fact_proposal_is_bounded_idempotent_and_does_not_mutate_source(
    tmp_path: Path,
) -> None:
    root = _authority_repo(tmp_path)
    source = root / SOURCE_ROOT / "00_AUTHORITY.md"
    before = source.read_bytes()
    first, first_path = emit_stale_source_proposal(
        proposal_root=root / "runtime/source-proposals",
        work_item_id="V3-MKT-007",
        group="current_facts",
        freshness_status="STALE",
        now=datetime(2026, 8, 12, tzinfo=UTC),
    )
    second, second_path = emit_stale_source_proposal(
        proposal_root=root / "runtime/source-proposals",
        work_item_id="V3-MKT-007",
        group="current_facts",
        freshness_status="STALE",
        now=datetime(2026, 8, 12, tzinfo=UTC),
    )
    assert first.proposal_id == second.proposal_id
    assert first_path == second_path
    assert first.max_review_rounds == 2
    assert first.normative_source_mutated is False
    assert source.read_bytes() == before
