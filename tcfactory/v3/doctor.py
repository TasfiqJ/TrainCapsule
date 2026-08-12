"""Deterministic, read-only health checks for the factory and local product."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import Field

from tcfactory.github_sync import load_github_config
from tcfactory.v3.base import V3Model
from tcfactory.v3.configuration import validate_v3_configuration


class DoctorCheck(V3Model):
    name: str
    status: Literal["PASS", "FAIL"]
    detail: str


class DoctorReport(V3Model):
    version: Literal[3] = 3
    healthy: bool
    network_used: Literal[False] = False
    checks: list[DoctorCheck] = Field(min_length=1)
    runtime_controls: dict[str, bool]


def _check(name: str, callback: Callable[[], str]) -> DoctorCheck:
    try:
        return DoctorCheck(name=name, status="PASS", detail=callback())
    except Exception as exc:  # every check must report instead of masking later failures
        return DoctorCheck(name=name, status="FAIL", detail=f"{type(exc).__name__}: {exc}")


def package_contracts(repo_root: Path) -> str:
    packages = {
        "traincapsule-core": ("traincapsule_core", None),
        "traincapsule-ingest-pytorch": ("traincapsule_ingest_pytorch", None),
        "traincapsule-qualify": ("traincapsule_qualify", None),
        "traincapsule-cli": ("traincapsule_cli", "traincapsule_cli.cli:main"),
    }
    for distribution, (module, entry_point) in packages.items():
        root = repo_root / "packages" / distribution
        manifest = root / "pyproject.toml"
        source = root / "src" / module / "__init__.py"
        if not manifest.is_file() or not source.is_file():
            raise RuntimeError(f"missing package manifest or import root: {distribution}")
        payload = tomllib.loads(manifest.read_text(encoding="utf-8"))
        project = payload.get("project", {})
        if project.get("name") != distribution:
            raise RuntimeError(f"package name mismatch: {distribution}")
        if entry_point and project.get("scripts", {}).get("traincapsule") != entry_point:
            raise RuntimeError("traincapsule installed entry point is missing or changed")
    return "four independent package manifests and the traincapsule entry point are present"


def _product_import_probe(repo_root: Path) -> str:
    source_roots = [str(path) for path in sorted((repo_root / "packages").glob("*/src"))]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [*source_roots, environment.get("PYTHONPATH", "")]
    )
    code = (
        "import traincapsule_core, traincapsule_ingest_pytorch, traincapsule_qualify; "
        "from traincapsule_cli.cli import main; "
        "assert callable(main)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "import probe failed").strip().splitlines()[-1]
        raise RuntimeError(tail[:500])
    return "factory interpreter can import all product packages and the CLI entry callable"


def _schema_freshness(repo_root: Path) -> str:
    source_roots = [str(path) for path in sorted((repo_root / "packages").glob("*/src"))]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root), *source_roots, environment.get("PYTHONPATH", "")]
    )
    scripts = (
        "scripts/generate_v3_schemas.py",
        "scripts/generate_product_schemas.py",
    )
    for script in scripts:
        result = subprocess.run(
            [sys.executable, script, "--check"],
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "schema check failed").strip()
            raise RuntimeError(f"{script}: {detail[-500:]}")
    return "factory and product schemas match their executable models"


def _source_integrity(repo_root: Path) -> str:
    from scripts.gates.source_of_truth_integrity import validate_repository

    validate_repository(repo_root)
    return "active V3.1 source generation and context digests are valid"


def _configuration(repo_root: Path) -> str:
    loaded = validate_v3_configuration(repo_root)
    github = load_github_config(repo_root / "config/github.yaml")
    if github.direct_main_push or github.publisher_capability == "PENDING_PHASE_4":
        raise RuntimeError(
            "V3.1 automated PR publisher/verifier is not installed; factory is fail-closed"
        )
    return f"validated {len(loaded)} V3.1 configurations and PR-only publication policy"


def _root_entry_point(repo_root: Path) -> str:
    payload = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    if payload.get("project", {}).get("scripts", {}).get("tcfactory") != "tcfactory.cli:app":
        raise RuntimeError("tcfactory installed entry point is missing or changed")
    return "tcfactory entry point is declared"


def json_readability(repo_root: Path) -> str:
    for path in sorted((repo_root / "schemas").rglob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
    return "all committed JSON schemas parse"


def collect_doctor_report(repo_root: Path) -> DoctorReport:
    root = repo_root.resolve()
    checks = [
        _check("factory-configuration", lambda: _configuration(root)),
        _check("source-integrity", lambda: _source_integrity(root)),
        _check("factory-entry-point", lambda: _root_entry_point(root)),
        _check("product-package-contracts", lambda: package_contracts(root)),
        _check("product-import-runtime", lambda: _product_import_probe(root)),
        _check("schema-json", lambda: json_readability(root)),
        _check("schema-freshness", lambda: _schema_freshness(root)),
    ]
    controls = {
        name: (root / "factory/state" / name).exists()
        for name in ("STOP", "PAUSE", "HARD_STUCK.json")
    }
    checks.append(
        DoctorCheck(
            name="runtime-controls",
            status="FAIL" if controls["HARD_STUCK.json"] else "PASS",
            detail=(
                "HARD_STUCK requires recovery"
                if controls["HARD_STUCK.json"]
                else "runtime controls are readable; STOP/PAUSE are reported without being mutated"
            ),
        )
    )
    return DoctorReport(
        healthy=all(check.status == "PASS" for check in checks),
        checks=checks,
        runtime_controls=controls,
    )
