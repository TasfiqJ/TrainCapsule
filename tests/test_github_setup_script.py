from __future__ import annotations

from pathlib import Path


def test_legacy_github_setup_fails_closed_without_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "configure_github.sh").read_text(encoding="utf-8")
    assert "exit 64" in text
    for forbidden in (
        "gh auth",
        "gh repo",
        "gh api",
        "git fetch",
        "git push",
        "config/github.yaml",
        "read -r",
    ):
        assert forbidden not in text


def test_factory_commit_messages_are_short_and_simple() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "tcfactory" / "commit_messages.py").read_text(encoding="utf-8")
    assert "_MAX_SUBJECT = 72" in text
    assert "feat" in text or "CommitType" in text
