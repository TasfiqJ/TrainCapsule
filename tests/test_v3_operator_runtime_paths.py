from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import typer

import tcfactory.cli as cli
from tcfactory.runtime_status import build_runtime_status
from tcfactory.v3.configuration import FactoryV3Config
from tcfactory.v3.queue import V3Queue
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
