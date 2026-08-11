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
        "value",
        "peers",
        "blocker",
        "features",
        "github",
        "sync",
    ):
        assert action in bash.lower()
    for action in ("Overview", "Start", "Pause", "Resume", "Stop", "Verify", "Recover", "Logs"):
        assert action in powershell
    assert "source scripts/load_factory_env.sh" in powershell
    assert "cd '$repository' && uv run" not in powershell
    assert "--force" not in bash
    assert "push --force" not in bash
