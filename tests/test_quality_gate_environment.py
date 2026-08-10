from pathlib import Path


def test_python_quality_gates_use_the_pinned_shared_environment() -> None:
    root = Path(__file__).resolve().parents[1]

    for name in ("fast_quality.sh", "full_quality.sh"):
        script = (root / "scripts" / "gates" / name).read_text(encoding="utf-8")
        assert "git rev-parse --path-format=absolute --git-common-dir" in script
        assert 'SHARED_VENV="$(dirname "$COMMON_GIT_DIR")/.venv"' in script
        assert 'export VIRTUAL_ENV="$SHARED_VENV"' in script
        assert "export UV_OFFLINE=1" in script
        assert '"$UV_BIN" run --active --no-sync ruff check .' in script
        assert '"$UV_BIN" run --active --no-sync pyright' in script
        assert '"$UV_BIN" run --active --no-sync python -m pytest -q' in script
