from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.gates.v3_1_zh_package_integrity import REPORT, ROOT, validate_package


def test_v31_package_gate_binds_all_43_split_payloads() -> None:
    assert validate_package(ROOT) == 43


def test_v31_package_gate_rejects_self_rebound_report(tmp_path: Path) -> None:
    report = tmp_path / REPORT.name
    payload = cast(dict[str, Any], json.loads(REPORT.read_text(encoding="utf-8")))
    entries = cast(list[dict[str, Any]], payload["entries"])
    entries[0]["sha256"] = "0" * 64
    entries[0]["actualSha256"] = "0" * 64
    report.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="report digest mismatch"):
        validate_package(ROOT, report_path=report)


def test_v2_historical_source_tamper_fails_locked_manifest(tmp_path: Path) -> None:
    source = tmp_path / "v2-source"
    shutil.copytree(ROOT / "docs/source-of-truth/final-2026-08-09", source)
    target = next(path for path in source.iterdir() if path.name != "FINAL_MANIFEST.json")
    target.chmod(target.stat().st_mode | stat.S_IWUSR)
    target.write_bytes(target.read_bytes() + b"\ntampered\n")
    completed = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "scripts/gates/validate_source_manifest.py",
            str(source),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "source file" in completed.stderr.lower()
