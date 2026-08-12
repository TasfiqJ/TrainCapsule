from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas/product"
EXPECTED = {
    "eligibility-decision.schema.json",
    "environment-identity.schema.json",
    "evidence-artifact.schema.json",
    "evidence-completeness-report.schema.json",
    "flight-recorder-import.schema.json",
    "incident-case.schema.json",
    "native-baseline.schema.json",
    "native-finding.schema.json",
    "preflight-inputs.schema.json",
    "workload-identity.schema.json",
}


def test_committed_product_schemas_are_current_strict_utf8_and_lf() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "packages/traincapsule-core/src"),
            str(ROOT / "packages/traincapsule-ingest-pytorch/src"),
            str(ROOT / "packages/traincapsule-qualify/src"),
            str(ROOT / "packages/traincapsule-cli/src"),
        ]
    )
    completed = subprocess.run(
        [sys.executable, "scripts/generate_product_schemas.py", "--check"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert {path.name for path in SCHEMA_ROOT.glob("*.json")} == EXPECTED
    for path in SCHEMA_ROOT.glob("*.json"):
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        assert b"\r" not in raw
        schema = json.loads(raw.decode("utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False


def test_product_packages_do_not_import_factory_domain_types() -> None:
    product_sources = list((ROOT / "packages").glob("traincapsule-*/src/**/*.py"))
    assert product_sources
    for source in product_sources:
        assert "tcfactory" not in source.read_text(encoding="utf-8"), source


def test_migration_report_file_inventory_is_current() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/update_v3_migration_inventory.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0


def test_migration_inventory_ignores_untracked_ci_artifacts(tmp_path: Path) -> None:
    artifact = ROOT / ".ci-artifacts" / "inventory-negative-control.log"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(str(tmp_path), encoding="utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, "scripts/update_v3_migration_inventory.py", "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0
    finally:
        artifact.unlink(missing_ok=True)
