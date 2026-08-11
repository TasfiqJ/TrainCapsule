from pathlib import Path


def test_unified_control_scripts_exist_and_cover_qol_actions() -> None:
    root = Path(__file__).resolve().parents[1]
    bash = (root / "scripts/factory_control.sh").read_text(encoding="utf-8")
    powershell = (root / "Control-TrainCapsuleBuilder.ps1").read_text(encoding="utf-8")
    for action in (
        "overview",
        "start",
        "pause",
        "resume",
        "stop",
        "verify",
        "recover",
        "logs",
        "queue",
        "costs",
        "roadmap",
        "schedule-dry-run",
        "milestone-status",
        "value",
        "peers",
        "blocker",
        "features",
        "github",
        "sync",
    ):
        assert action in bash.lower()
    for action in (
        "Status",
        "Start",
        "Pause",
        "Resume",
        "Stop",
        "Verify",
        "Recover",
        "Logs",
        "ScheduleDryRun",
        "MilestoneStatus",
    ):
        assert action in powershell
    assert "$RepoPath = $env:TCF_REPO_PATH" in powershell
    assert "$WslDistribution = $env:TCF_WSL_DISTRIBUTION" in powershell
    assert '$FactoryRuntimePath = "scripts/factory_control.sh"' in powershell
    assert "/home/jasim" not in powershell
    assert "Ubuntu-22.04" not in powershell
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in powershell
    assert "cd '$repository' && uv run" not in powershell
    assert "--force" not in bash
    assert "push --force" not in bash
