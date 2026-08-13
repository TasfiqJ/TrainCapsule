from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from tcfactory.v3.doctor import json_readability, package_contracts
from tcfactory.v3.pilot import create_pilot_metadata, load_pilot_metadata

ROOT = Path(__file__).resolve().parents[1]


def _copy_active_authority(destination: Path) -> None:
    shutil.copytree(ROOT / "config", destination / "config")
    shutil.copytree(ROOT / "docs/source-of-truth", destination / "docs/source-of-truth")
    shutil.copytree(
        ROOT / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
        destination / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
    )
    (destination / "docs").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs/CONTEXT_INDEX.yaml", destination / "docs/CONTEXT_INDEX.yaml")
    (destination / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/generate_v3_1_zh_source.py",
        destination / "scripts/generate_v3_1_zh_source.py",
    )


def _copy_package_contracts(destination: Path) -> None:
    for source in sorted((ROOT / "packages").glob("traincapsule-*")):
        target = destination / "packages" / source.name
        (target / "src").mkdir(parents=True)
        shutil.copy2(source / "pyproject.toml", target / "pyproject.toml")
        for module_root in (source / "src").iterdir():
            copied = target / "src" / module_root.name
            copied.mkdir()
            shutil.copy2(module_root / "__init__.py", copied / "__init__.py")


def test_doctor_rejects_broken_product_entry_point_and_schema(tmp_path: Path) -> None:
    _copy_package_contracts(tmp_path)
    assert "four independent" in package_contracts(tmp_path)

    cli_manifest = tmp_path / "packages/traincapsule-cli/pyproject.toml"
    cli_manifest.write_text(
        cli_manifest.read_text(encoding="utf-8").replace(
            'traincapsule = "traincapsule_cli.cli:main"',
            'traincapsule = "traincapsule_cli.cli:missing"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="entry point"):
        package_contracts(tmp_path)

    schema = tmp_path / "schemas/product/broken.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json_readability(tmp_path)


def test_pilot_metadata_is_content_addressed_and_never_evidence(tmp_path: Path) -> None:
    _copy_active_authority(tmp_path)
    created = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)

    path = create_pilot_metadata(tmp_path, "pilot-001", created_at=created)
    _, record = load_pilot_metadata(tmp_path, "pilot-001")
    assert path.stem == record.canonical_digest().removeprefix("sha256:")
    assert record.evidence_authority == "NONE"
    assert record.decision_authority == "NONE"
    assert record.commercial_maturity == "UNKNOWN"
    assert record.external_evidence_refs == []
    assert record.automatic_promotion is False
    with pytest.raises(ValueError, match="already exists"):
        create_pilot_metadata(tmp_path, "pilot-001", created_at=created)

    path.chmod(0o644)
    payload = path.read_text(encoding="utf-8").replace("LOCAL_DRAFT", "VALIDATED")
    path.write_text(payload, encoding="utf-8")
    with pytest.raises((ValueError, ValidationError)):
        load_pilot_metadata(tmp_path, "pilot-001")


def test_pilot_id_cannot_escape_local_state(tmp_path: Path) -> None:
    _copy_active_authority(tmp_path)
    with pytest.raises(ValidationError):
        create_pilot_metadata(tmp_path, "../../escape")
