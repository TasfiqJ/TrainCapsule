from __future__ import annotations

from pathlib import Path

import pytest

from scripts.gates import gate_common


def test_match_files_preserves_leading_dot_for_hidden_authority_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hidden = tmp_path / ".factory/external-evidence/T001.json"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(gate_common, "ROOT", tmp_path)

    assert gate_common.match_files(".factory/external-evidence/T001.json") == [hidden]


def test_match_files_removes_only_an_explicit_current_directory_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    visible = tmp_path / "docs/evidence.txt"
    visible.parent.mkdir(parents=True)
    visible.write_text("evidence\n", encoding="utf-8")
    monkeypatch.setattr(gate_common, "ROOT", tmp_path)

    assert gate_common.match_files("./docs/evidence.txt") == [visible]
