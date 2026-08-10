from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tcfactory.cli import validate_calibration_evidence

REQUIRED_CONTROLS = [
    "max_oauth_verify",
    "schema_generation",
    "unit_tests",
    "ruff",
    "pyright",
    "deterministic_sabotage",
    "private_gate_self_test",
    "private_gate_repository",
    "live_demo",
    "claude_native_features",
    "cross_session_messaging",
]


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _make_valid_evidence(repo: Path) -> Path:
    _git(repo, "init", "-b", "main")
    (repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
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
    head = _git(repo, "rev-parse", "HEAD")
    artifact = repo / "factory/artifacts/DEMO-001/run-1"
    artifact.mkdir(parents=True)
    summary = artifact / "pipeline-summary.json"
    builder_dir = artifact / "builder-a1"
    scout_dir = builder_dir / "integration-scout"
    scout_dir.mkdir(parents=True)
    (builder_dir / "peer-messages.jsonl").write_text(
        '{"sender":"builder","recipient":"scout"}\n', encoding="utf-8"
    )
    (scout_dir / "peer-messages.jsonl").write_text(
        '{"sender":"scout","recipient":"builder"}\n', encoding="utf-8"
    )
    (builder_dir / "claude-native-feature-plan.json").write_text(
        json.dumps(
            {
                "peer_messaging": True,
                "goal_condition": "all checks pass",
                "advisor_model": "opus",
                "skills": ["implement-task"],
            }
        ),
        encoding="utf-8",
    )
    (scout_dir / "claude-native-feature-plan.json").write_text(
        json.dumps({"peer_messaging": True, "skills": ["integration-proof"]}),
        encoding="utf-8",
    )
    results: list[dict[str, object]] = []
    for index, role in enumerate(["specification", "adversary", "audit", "release"], start=1):
        results.append({"role": role, "verdict": "pass", "session_id": f"session-{index}"})
    results.insert(
        1,
        {
            "role": "builder",
            "verdict": "pass",
            "session_id": "session-builder",
            "peer_messaging_enabled": True,
            "artifact_dir": str(builder_dir),
            "peer_sessions": [
                {
                    "role": "integration_scout",
                    "verdict": "pass",
                    "session_id": "session-scout",
                    "artifact_dir": str(scout_dir),
                }
            ],
        },
    )
    summary.write_text(
        json.dumps(
            {
                "task_id": "DEMO-001",
                "run_id": "run-1",
                "starting_sha": head,
                "final_sha": "candidate-sha",
                "merged": False,
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    log_dir = repo / "factory/state/calibration"
    log_dir.mkdir(parents=True)
    logs: list[dict[str, object]] = []
    for name in REQUIRED_CONTROLS:
        path = log_dir / f"{name}.stdout.log"
        path.write_text(f"{name} passed\n", encoding="utf-8")
        logs.append(
            {
                "path": str(path.relative_to(repo)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
        )
    evidence = repo / "factory/state/CALIBRATION_EVIDENCE.json"
    evidence.write_text(
        json.dumps(
            {
                "version": 3,
                "head_sha": head,
                "live_pipeline_summary": str(summary.relative_to(repo)),
                "summary_sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
                "required_controls": REQUIRED_CONTROLS,
                "logs": logs,
            }
        ),
        encoding="utf-8",
    )
    return evidence


def test_valid_calibration_evidence_passes(tmp_path: Path) -> None:
    _make_valid_evidence(tmp_path)
    result = validate_calibration_evidence(tmp_path)
    assert result["version"] == 3


def test_calibration_script_uses_pinned_python_for_evidence() -> None:
    script = Path("scripts/run_one_time_calibration.sh").read_text(encoding="utf-8")

    assert 'uv run python - "$SUMMARY" "$EVIDENCE_DIR"' in script
    assert 'python3 - "$SUMMARY" "$EVIDENCE_DIR"' not in script


def test_tampered_calibration_log_fails(tmp_path: Path) -> None:
    _make_valid_evidence(tmp_path)
    path = tmp_path / "factory/state/calibration/unit_tests.stdout.log"
    path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        validate_calibration_evidence(tmp_path)
