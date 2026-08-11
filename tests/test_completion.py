from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.completion import deterministic_completion_check
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_completion_check_requires_paths_and_commands(tmp_path: Path) -> None:
    (tmp_path / "present.txt").write_text("ok", encoding="utf-8")
    definition = {
        "required_paths": ["present.txt", "missing.txt"],
        "required_globs": ["*.txt", "capsules/**/capsule.json"],
        "required_commands": [
            {"name": "passes", "command": "test -f present.txt", "timeout_seconds": 5},
            {"name": "fails", "command": "exit 7", "timeout_seconds": 5},
        ],
    }
    failures = deterministic_completion_check(tmp_path, definition)
    assert any("Missing required path: missing.txt" in value for value in failures)
    assert any(
        "No files matched required glob: capsules/**/capsule.json" in value for value in failures
    )
    assert any("Completion command 'fails' failed (7)" in value for value in failures)
    assert not any("passes" in value for value in failures)


def test_product_completion_requires_commercialization_ready_production_evidence() -> None:
    definition = load_yaml(ROOT / "factory/product_definition_of_done.yaml")
    required_paths = set(definition["required_paths"])
    assert {
        "docs/product/BUYER_AND_USER_WORKFLOWS.md",
        "docs/product/INSTALL_DEPLOY_UPGRADE.md",
        "docs/product/OPERATIONS_SUPPORT_AND_FAILURES.md",
        "docs/product/COMMERCIAL_READINESS.md",
        "docs/product/EXTERNAL_VALIDATION_PACKET.md",
    }.issubset(required_paths)

    readiness = definition["commercial_readiness_evidence_required"]
    assert any("economic buyer" in item for item in readiness)
    assert any("privacy-safe" in item for item in readiness)
    assert any("EXTERNAL_VALIDATION_REQUIRED" in item for item in readiness)

    quality_floor = definition["quality_floor"]
    assert any("mock-only" in item for item in quality_floor)
    assert any("end-to-end" in item for item in quality_floor)


def test_private_completion_gate_runs_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from tcfactory.completion import run_private_completion_gate
    from tcfactory.models import FactoryConfig

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    private = tmp_path / "private"
    private.mkdir()
    runner = private / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'test "$1" = product-completion\n'
        'test "$2" = "$TCF_CANDIDATE_WORKTREE"\n'
        'test "$TCF_TASK_ID" = PRODUCT_COMPLETION\n',
        encoding="utf-8",
    )
    runner.chmod(0o700)
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", str(runner))
    config = FactoryConfig(auth_mode="unrestricted")
    payload = run_private_completion_gate(
        repo_root=repo,
        config=config,
        run_id="completion-test",
    )
    assert payload["passed"] is True
