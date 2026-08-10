from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.completion import deterministic_completion_check


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
