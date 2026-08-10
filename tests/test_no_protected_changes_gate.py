from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PROTECTED_FILES = [
    "docs/source-of-truth/final-2026-08-09/README.md",
    ".factory/source-locks/manifest.json",
    ".claude/settings.json",
    "config/factory.yaml",
    "prompts/builder.md",
    "schemas/task.schema.json",
    "tcfactory/runner.py",
    "scripts/other.sh",
    "bootstrap/private-gates/runner.sh",
    "factory/task_catalog.yaml",
    "factory/feature_ledger.yaml",
    "factory/product_definition_of_done.yaml",
]


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("relative", PROTECTED_FILES)
def test_calibration_gate_rejects_every_protected_root(tmp_path: Path, relative: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    gate = repo / "scripts/gates/no_protected_changes.sh"
    gate.parent.mkdir(parents=True)
    source_gate = Path(__file__).parents[1] / "scripts/gates/no_protected_changes.sh"
    gate.write_text(source_gate.read_text(encoding="utf-8"), encoding="utf-8")

    protected = repo / relative
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text("original\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "candidate")

    protected.write_text("changed\n", encoding="utf-8")
    _git(repo, "add", relative)
    _git(repo, "commit", "-m", "mutate protected file")

    result = subprocess.run(["bash", str(gate)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Protected factory files changed" in result.stderr


def test_calibration_gate_allows_only_demo_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    gate = repo / "scripts/gates/no_protected_changes.sh"
    gate.parent.mkdir(parents=True)
    source_gate = Path(__file__).parents[1] / "scripts/gates/no_protected_changes.sh"
    gate.write_text(source_gate.read_text(encoding="utf-8"), encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "candidate")
    output = repo / "demo/checksum.py"
    output.parent.mkdir()
    output.write_text("pass\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add demo output")

    result = subprocess.run(["bash", str(gate)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
