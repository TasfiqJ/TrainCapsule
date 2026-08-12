from __future__ import annotations

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.backends.base import BackendRouteState
from tcfactory.runtime_status import build_runtime_status
from tcfactory.supervisor import (
    MigrationCompleteMarker,
    RuntimePaths,
    SupervisorState,
    record_controller_exit,
    run_startup_preflight,
    save_supervisor_state,
)
from tcfactory.util import sha256_file, write_json
from tcfactory.v3.configuration import load_autonomy_v3, load_factory_v3
from tcfactory.v3.private_gate import PrivateGateHealthCheck, PrivateGateVerificationError


def _runtime_paths(root: Path) -> RuntimePaths:
    return RuntimePaths(
        state_root=root,
        migration_marker=root / "MIGRATION_COMPLETE_V3.json",
        supervisor_state=root / "supervisor-state.json",
        supervisor_lock=root / "supervisor.lock",
        hard_stuck=root / "HARD_STUCK.json",
        stop=root / "STOP",
    )


def _patch_policy(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path, runtime_root: Path
) -> RuntimePaths:
    config = load_factory_v3(repo_root / "config" / "factory.yaml")
    autonomy = load_autonomy_v3(repo_root / "config" / "autonomy.yaml")
    paths = _runtime_paths(runtime_root)
    monkeypatch.setattr("tcfactory.supervisor._factory_config", lambda _: config)
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_v3_configuration",
        lambda _: {"factory": config, "autonomy": autonomy},
    )
    monkeypatch.setattr("tcfactory.supervisor.runtime_paths", lambda *_: paths)
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_private_gate_installation",
        lambda *_args, **_kwargs: (Path("/trusted/runner"), Path("/trusted/key")),
    )
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_private_gate_runtime_health",
        lambda *_args, **_kwargs: PrivateGateHealthCheck(),
    )
    return paths


def test_supervisor_uses_exact_finite_restart_sequence_then_hard_stuck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    paths = _patch_policy(monkeypatch, repo_root, tmp_path)
    now = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)

    decisions = [
        record_controller_exit(repo_root=repo_root, runtime_seconds=10, exit_code=1, now=now)
        for _ in range(4)
    ]

    assert [decision.delay_seconds for decision in decisions] == [15, 60, 300, 0]
    assert [decision.action for decision in decisions] == [
        "RESTART",
        "RESTART",
        "RESTART",
        "HARD_STUCK",
    ]
    assert paths.hard_stuck.is_file()
    assert paths.stop.is_file()


def test_healthy_interval_is_the_only_restart_budget_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    paths = _patch_policy(monkeypatch, repo_root, tmp_path)
    save_supervisor_state(paths.supervisor_state, SupervisorState(restart_attempts=3))

    decision = record_controller_exit(
        repo_root=repo_root,
        runtime_seconds=1800,
        exit_code=2,
        now=datetime(2026, 8, 11, 21, 0, tzinfo=UTC),
    )

    assert decision.action == "RESTART"
    assert decision.delay_seconds == 15
    assert decision.restart_attempts == 1
    assert decision.budget_reset is True


def test_startup_preflight_requires_marker_credentials_and_clean_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    paths = _patch_policy(monkeypatch, repo_root, tmp_path)
    config = load_factory_v3(repo_root / "config" / "factory.yaml")
    from tcfactory.gitops import current_sha

    marker = MigrationCompleteMarker(
        completed_sha=current_sha(repo_root),
        source_manifest_sha256=sha256_file(repo_root / config.source_of_truth.manifest),
        active_generation_sha256=sha256_file(repo_root / "config/active_generation.yaml"),
        acceptance_work_items={f"V3-MIG-{number:03d}": "COMPLETED" for number in range(16, 21)},
        acceptance_evidence_digests={
            f"V3-MIG-{number:03d}": "sha256:" + "a" * 64 for number in range(16, 21)
        },
        completed_at=datetime(2026, 8, 11, 21, 0, tzinfo=UTC),
    )
    write_json(paths.migration_marker, marker.model_dump(mode="json", by_alias=True))
    monkeypatch.setattr("tcfactory.supervisor._verify_migration_marker", lambda *_: marker)
    monkeypatch.setattr("tcfactory.supervisor._verify_source_integrity", lambda _: None)
    monkeypatch.setattr(
        "tcfactory.supervisor.verify_legacy_queue_archive_receipt", lambda *_, **__: {}
    )

    class AuthenticatedProvider:
        def __init__(self, *, require_long_lived_token: bool = False) -> None:
            assert require_long_lived_token

        def state(self) -> BackendRouteState:
            return BackendRouteState.AUTHENTICATED

    monkeypatch.setattr("tcfactory.supervisor.ClaudeCredentialProvider", AuthenticatedProvider)

    with pytest.raises(RuntimeError, match="publisher/verifier capability is pending"):
        run_startup_preflight(repo_root)
    return

    def reject_private_gate(*_args: object, **_kwargs: object) -> tuple[Path, Path]:
        raise PrivateGateVerificationError("mandatory gate missing")

    monkeypatch.setattr(
        "tcfactory.supervisor.validate_private_gate_installation", reject_private_gate
    )
    with pytest.raises(PrivateGateVerificationError, match="mandatory gate missing"):
        run_startup_preflight(repo_root)
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_private_gate_installation",
        lambda *_args, **_kwargs: (Path("/trusted/runner"), Path("/trusted/key")),
    )

    paths.stop.write_text("stop\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="durable STOP"):
        run_startup_preflight(repo_root)


def test_startup_reconciles_publication_before_exact_sha_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    _patch_policy(monkeypatch, repo_root, tmp_path)
    with pytest.raises(RuntimeError, match="publisher/verifier capability is pending"):
        run_startup_preflight(repo_root)


def test_v3_status_exposes_required_operator_fields() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    status = build_runtime_status(repo_root)

    assert status["activeMilestone"] == "M0_FACTORY_MIGRATED"
    assert set(status["currentWorkItem"]) == {"workItemId", "lane", "status"}
    assert set(status["retryBudget"]) == {
        "planAttemptsRemaining",
        "repairCyclesRemaining",
        "candidateRestartsRemaining",
    }
    assert {"used", "maximum", "remaining", "healthyResetSeconds"} <= set(status["restartBudget"])
    for field in (
        "interventionMode",
        "externalBlockers",
        "candidateSha",
        "factoryCi",
        "productCi",
        "lastMainPublication",
    ):
        assert field in status
    assert status["interventionMode"] == "NONE"
