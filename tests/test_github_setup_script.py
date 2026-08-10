from __future__ import annotations

from pathlib import Path


def test_github_setup_is_private_https_and_never_force_pushes() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "configure_github.sh").read_text(encoding="utf-8")
    assert "--git-protocol https" in text
    assert "--private" in text
    assert 'visibility" != "private"' in text
    assert "git push -u origin main" in text
    assert "git push --force" not in text
    assert "never force-push" in text


def test_factory_commit_messages_are_short_and_simple() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "tcfactory" / "commit_messages.py").read_text(encoding="utf-8")
    assert "_MAX_SUBJECT = 72" in text
    assert "feat" in text or "CommitType" in text
