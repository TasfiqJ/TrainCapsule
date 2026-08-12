from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from tcfactory.cli import app

ROOT = Path(__file__).resolve().parents[1]


def test_v31_legacy_mutation_commands_reject_before_mutation() -> None:
    runner = CliRunner()
    before = (ROOT / "factory/feature_ledger.yaml").read_bytes()
    commands = (
        ["github-sync", "--repo", str(ROOT)],
        ["enqueue", "tasks/T002.yaml", "--repo", str(ROOT)],
        ["worker", "--repo", str(ROOT)],
        ["queue-reconcile", "--repo", str(ROOT)],
        ["recover", "--repo", str(ROOT)],
    )
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code != 0
        observed = result.output or str(result.exception)
        assert "disabled V2 compatibility surface" in observed
    assert (ROOT / "factory/feature_ledger.yaml").read_bytes() == before


def test_historical_finalizer_cannot_mutate_v31_pending_receipts() -> None:
    root = ROOT / "docs/migrations/evidence/v3.1-zh"
    before = {path.name: path.read_bytes() for path in root.glob("*.json")}
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "scripts/finalize_v3_m0_evidence.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "cannot finalize V3.1 M0" in completed.stderr
    assert {path.name: path.read_bytes() for path in root.glob("*.json")} == before


def test_local_simulation_cannot_finalize_v31_mig016_or_mig019() -> None:
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "scripts/finalize_v3_1_zh_m0_evidence.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "independent receipts are missing" in completed.stderr
