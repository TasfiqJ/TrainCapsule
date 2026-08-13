from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import typer

import tcfactory.cli as cli
from tcfactory.runtime_status import build_runtime_status
from tcfactory.v3.configuration import FactoryV3Config
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.runtime_paths import ensure_v3_mutable_runtime, resolve_v3_runtime_paths
from tcfactory.v3.work_items import WorkItem, WorkItemCollection
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def _item() -> WorkItem:
    collection = WorkItemCollection.model_validate(
        load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    )
    return collection.work_items[0]


def test_all_v3_operator_reads_and_recovery_share_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(runtime_root))
    queue = V3Queue(runtime_root / "v3-queue")
    queue.put(_item())

    cli.queue_status(repo=ROOT, config_path=Path("config/factory.yaml"))
    assert str(runtime_root / "v3-queue") in capsys.readouterr().out
    cli.status(repo=ROOT, config_path=Path("config/factory.yaml"))
    assert str(runtime_root / "v3-queue") in capsys.readouterr().out
    cli.explain_blocker(repo=ROOT, config_path=Path("config/factory.yaml"))
    assert str(runtime_root / "v3-queue") in capsys.readouterr().out
    cli.recover(repo=ROOT, config_path=Path("config/factory.yaml"))
    assert str(runtime_root / "v3-queue") in capsys.readouterr().out
    cli.verify_factory(repo=ROOT, config_path=Path("config/factory.yaml"))
    assert str(runtime_root / "v3-queue") in capsys.readouterr().out
    assert build_runtime_status(ROOT)["queueRoot"] == str(runtime_root / "v3-queue")
    assert not (ROOT / "factory/queue/v3").exists()


def test_start_is_v3_only_and_never_clears_runtime_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(runtime_root))
    called: list[tuple[Path, bool]] = []

    def fake_controller(*, repo: Path, once: bool) -> None:
        called.append((repo, once))

    monkeypatch.setattr(cli, "v3_controller", fake_controller)
    cli.start(repo=ROOT, config_path=Path("config/factory.yaml"), once=True)
    assert called == [(ROOT, True)]

    runtime_root.mkdir(parents=True, exist_ok=True)
    pause = runtime_root / "PAUSE"
    pause.write_text("pause\n", encoding="utf-8")
    with pytest.raises(typer.Exit):
        cli.start(repo=ROOT, config_path=Path("config/factory.yaml"), once=True)
    assert pause.is_file()
    assert called == [(ROOT, True)]

    legacy = tmp_path / "legacy"
    (legacy / "config").mkdir(parents=True)
    (legacy / "config/factory.yaml").write_text("version: 2\n", encoding="utf-8")
    with pytest.raises(typer.Exit):
        cli.start(repo=legacy, config_path=Path("config/factory.yaml"), once=True)
    assert called == [(ROOT, True)]


def test_alternate_v2_config_cannot_reach_legacy_v2_control_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(runtime_root))
    alternate = tmp_path / "attacker-v2.yaml"
    alternate.write_text(
        "version: 2\nautonomy_config_path: attacker-autonomy.yaml\n"
        "autonomy_state_path: attacker-state.json\n",
        encoding="utf-8",
    )
    legacy_pause = ROOT / "factory/state/PAUSE"
    legacy_stop = ROOT / "factory/state/STOP"
    before = {
        legacy_pause: legacy_pause.read_bytes() if legacy_pause.exists() else None,
        legacy_stop: legacy_stop.read_bytes() if legacy_stop.exists() else None,
    }

    cli.autonomy_pause(repo=ROOT, config_path=alternate)
    assert (runtime_root / "PAUSE").read_bytes() == b"pause requested\n"
    assert {path: path.read_bytes() if path.exists() else None for path in before} == before

    cli.autonomy_resume(repo=ROOT, config_path=alternate)
    assert not (runtime_root / "PAUSE").exists()

    cli.autonomy_stop(repo=ROOT, config_path=alternate)
    assert (runtime_root / "STOP").read_bytes() == b"stop requested\n"
    with pytest.raises(typer.Exit):
        cli.autonomy_resume(repo=ROOT, config_path=alternate)
    assert {path: path.read_bytes() if path.exists() else None for path in before} == before


def test_alternate_v2_config_cannot_bypass_any_disabled_v2_mutator(tmp_path: Path) -> None:
    alternate = tmp_path / "attacker-v2.yaml"
    alternate.write_text("version: 2\n", encoding="utf-8")
    with pytest.raises(typer.BadParameter, match="disabled V2 compatibility surface"):
        cli._reject_legacy_v2_surface(  # pyright: ignore[reportPrivateUsage]
            ROOT, alternate, "worker"
        )


def test_mutable_git_anchor_accepts_only_exact_private_empty_installer_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(runtime_root))
    paths = resolve_v3_runtime_paths(ROOT)
    paths.state_root.mkdir(mode=0o700)
    paths.git_root.mkdir(parents=True, mode=0o700)
    ensure_v3_mutable_runtime(ROOT, paths)
    assert (paths.git_root / "HEAD").is_file()

    substituted = tmp_path / "substituted"
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(substituted))
    substituted_paths = resolve_v3_runtime_paths(ROOT)
    substituted_paths.state_root.mkdir(mode=0o700)
    substituted_paths.git_root.mkdir(parents=True, mode=0o700)
    (substituted_paths.git_root / "attacker").write_text("not Git\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="mutable Git anchor validation failed"):
        ensure_v3_mutable_runtime(ROOT, substituted_paths)

    weak = tmp_path / "weak"
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(weak))
    weak_paths = resolve_v3_runtime_paths(ROOT)
    weak_paths.state_root.mkdir(mode=0o700)
    weak_paths.git_root.mkdir(parents=True, mode=0o755)
    with pytest.raises(RuntimeError, match="empty mutable Git anchor is not private"):
        ensure_v3_mutable_runtime(ROOT, weak_paths)


def test_controller_paths_honor_alternate_configured_runtime_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = load_yaml(ROOT / "config/factory.yaml")
    assert isinstance(raw, dict)
    typed = cast(dict[str, object], raw)
    runtime = typed["runtime"]
    assert isinstance(runtime, dict)
    cast(dict[str, object], runtime)["localStateRootEnvironmentVariable"] = (
        "TCF_ALTERNATE_V3_RUNTIME_ROOT"
    )
    factory = FactoryV3Config.model_validate(typed)
    alternate = (tmp_path / "alternate-runtime").resolve()
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    monkeypatch.setenv("TCF_ALTERNATE_V3_RUNTIME_ROOT", str(alternate))

    paths = cli.resolve_v3_runtime_paths(ROOT, factory)

    assert paths.state_root == alternate
    assert paths.machine_policy_receipts == alternate / "machine-policy-receipts"
    assert paths.quarantine == alternate / "quarantine"
    assert paths.controller_lock == alternate / "controller.lock"
