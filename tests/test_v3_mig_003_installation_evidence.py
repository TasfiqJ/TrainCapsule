from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = ROOT / "schemas/factory/v3/migration-installation-evidence.schema.json"
EVIDENCE_PATH = ROOT / "docs/migrations/evidence/V3-MIG-003.json"
GENERATOR = ROOT / "scripts/generate_v3_mig_003_evidence.py"
OLD_ROOT = Path("docs/source-of-truth/v3-2026-08-11")


def test_v3_mig_003_evidence_recomputes_exactly_and_validates_schema() -> None:
    subprocess.run([sys.executable, GENERATOR, "--check"], cwd=ROOT, check=True)
    checked_in = EVIDENCE_PATH.read_text(encoding="utf-8")
    payload = json.loads(checked_in)
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(  # pyright: ignore[reportUnknownMemberType]
        payload
    )
    assert payload["coverage"]["sourceHeadingCount"] == 504
    assert payload["coverage"]["mappedHeadingCount"] == 504
    assert payload["preservedOldAuthority"]["noPostInstallMutation"] is True


def test_v3_mig_003_rejects_unauthorized_old_tree_mutation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT, repo, symlinks=True, ignore=shutil.ignore_patterns(".venv"))
    authority = repo / OLD_ROOT / "00_EXECUTIVE_BUILD_DECISION_V3.md"
    authority.write_text(authority.read_text(encoding="utf-8") + "\nunauthorized\n")
    result = subprocess.run(
        [sys.executable, repo / "scripts/generate_v3_mig_003_evidence.py", "--repo-root", repo],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "changed after the V3.1-ZH installation" in result.stderr
