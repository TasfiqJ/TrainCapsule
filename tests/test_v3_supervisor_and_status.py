from __future__ import annotations

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.backends.base import BackendRouteState
from tcfactory.runtime_status import build_runtime_status
from tcfactory.supervisor import (
    MigrationCompleteMarker,
    RuntimePaths,
    SupervisorState,
    _verify_m0_observation_state,
    _verify_migration_marker,
    create_migration_complete_marker,
    record_controller_exit,
    run_startup_preflight,
    save_supervisor_state,
)
from tcfactory.util import read_json, sha256_file, write_json
from tcfactory.v3.configuration import load_autonomy_v3, load_factory_v3
from tcfactory.v3.enums import MilestoneStatus
from tcfactory.v3.milestone_runtime import (
    MilestoneRuntimeState,
    advance_milestone_state,
)
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.private_gate import PrivateGateHealthCheck, PrivateGateVerificationError
from tcfactory.v3.runtime_paths import resolve_v3_runtime_paths
from tcfactory.v3.source_authority import validate_active_source_generation
from tcfactory.yamlutil import load_yaml


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
        milestone_receipt_digest="sha256:" + "d" * 64,
        completed_at=datetime(2026, 8, 11, 21, 0, tzinfo=UTC),
    )
    write_json(paths.migration_marker, marker.model_dump(mode="json", by_alias=True))
    monkeypatch.setattr("tcfactory.supervisor._verify_migration_marker", lambda *_: marker)
    monkeypatch.setattr("tcfactory.supervisor._verify_source_integrity", lambda _: None)
    def verify_tracked_legacy_archive(
        _repo_root: Path, *, require_live: bool = True
    ) -> dict[str, object]:
        assert require_live is False
        return {}

    monkeypatch.setattr(
        "tcfactory.supervisor.verify_legacy_queue_archive_receipt",
        verify_tracked_legacy_archive,
    )

    class AuthenticatedProvider:
        def __init__(self, *, require_long_lived_token: bool = False) -> None:
            assert require_long_lived_token

        def state(self) -> BackendRouteState:
            return BackendRouteState.AUTHENTICATED

    monkeypatch.setattr("tcfactory.supervisor.ClaudeCredentialProvider", AuthenticatedProvider)
    monkeypatch.setattr("tcfactory.supervisor.validate_publication_installation", lambda *_: None)
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_controller_activation",
        lambda **_: "sha256:" + "b" * 64,
    )
    monkeypatch.setattr(
        "tcfactory.v3.activation.validate_activation_control_state", lambda **_: None
    )
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_repository_release_controls",
        lambda **_: {"status": "PASS", "rulesDigest": "sha256:" + "c" * 64},
    )
    monkeypatch.setattr("tcfactory.supervisor.reconcile_publications", lambda **_: [])

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
    paths.stop.unlink()

    result = run_startup_preflight(repo_root)
    assert result["ready"] is True
    assert result["publicationRecovery"] == {
        "status": "RECONCILED",
        "transactions": 0,
        "phases": [],
        "repositoryControls": {
            "status": "PASS",
            "rulesDigest": "sha256:" + "c" * 64,
        },
        "activationReceiptDigest": "sha256:" + "b" * 64,
    }


def test_m0_observation_is_the_only_markerless_migration_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = load_factory_v3(repo_root / "config" / "factory.yaml")
    monkeypatch.setenv(config.runtime.local_state_root_environment_variable, str(tmp_path))
    paths = resolve_v3_runtime_paths(repo_root, config)

    _verify_m0_observation_state(repo_root, config, paths)

    completed = MilestoneRuntimeState(
        active_milestone="M1_NATIVE_PREFLIGHT",
        statuses={
            "M0_FACTORY_MIGRATED": MilestoneStatus.COMPLETED,
            "M1_NATIVE_PREFLIGHT": MilestoneStatus.ACTIVE,
        },
        last_completion_digest="sha256:" + "a" * 64,
        updated_at=datetime(2026, 8, 14, 2, 0, tzinfo=UTC),
    )
    write_json(
        paths.milestone_state,
        {
            "record": completed.model_dump(mode="json", by_alias=True),
            "contentDigest": completed.canonical_digest(),
        },
    )
    with pytest.raises(RuntimeError, match="mandatory after M0 observation"):
        _verify_m0_observation_state(repo_root, config, paths)


def test_migration_marker_is_derived_from_immutable_m0_runtime_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = load_factory_v3(repo_root / "config" / "factory.yaml")
    monkeypatch.setenv(config.runtime.local_state_root_environment_variable, str(tmp_path))
    monkeypatch.setattr("tcfactory.supervisor._verify_source_integrity", lambda _: None)
    paths = resolve_v3_runtime_paths(repo_root, config)
    active_source = validate_active_source_generation(repo_root)
    required = {f"V3-MIG-{number:03d}" for number in range(16, 21)}
    evidence = {
        identifier: "sha256:" + str(index) * 64
        for index, identifier in enumerate(sorted(required), 1)
    }
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(repo_root / config.roadmap.milestones)
    )
    receipt_path = paths.milestone_decisions / "M0_FACTORY_MIGRATED.json"
    advance_milestone_state(
        roadmap=roadmap,
        state_path=paths.milestone_state,
        receipt_path=receipt_path,
        evidence_digests=evidence,
        expected_evidence_ids=required,
        source_authority_digest=active_source.canonical_digest(),
        now=datetime(2026, 8, 14, 2, 15, tzinfo=UTC),
    )

    marker = create_migration_complete_marker(repo_root)
    assert marker.acceptance_evidence_digests == evidence
    assert marker.milestone_receipt_digest == read_json(receipt_path, {})["contentDigest"]
    assert _verify_migration_marker(repo_root, config, paths.migration_marker) == marker

    from tcfactory.gitops import current_sha

    previous = marker.model_copy(update={"completed_sha": current_sha(repo_root, "HEAD^")})
    write_json(
        paths.migration_marker, previous.model_dump(mode="json", by_alias=True)
    )
    with pytest.raises(RuntimeError, match="exact current checkout SHA"):
        _verify_migration_marker(repo_root, config, paths.migration_marker)
    assert (
        _verify_migration_marker(
            repo_root,
            config,
            paths.migration_marker,
            allow_ancestor_completion=True,
        )
        == previous
    )
    marker = create_migration_complete_marker(repo_root)
    assert marker.completed_sha == current_sha(repo_root)

    raw = read_json(receipt_path, {})
    raw["contentDigest"] = "sha256:" + "f" * 64
    write_json(receipt_path, raw)
    with pytest.raises(RuntimeError, match="receipt digest mismatch"):
        _verify_migration_marker(repo_root, config, paths.migration_marker)


def test_startup_reconciles_publication_before_exact_sha_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    _patch_policy(monkeypatch, repo_root, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr("tcfactory.supervisor._verify_source_integrity", lambda _: None)
    monkeypatch.setattr(
        "tcfactory.supervisor.verify_legacy_queue_archive_receipt", lambda *_, **__: {}
    )
    monkeypatch.setattr("tcfactory.supervisor.validate_publication_installation", lambda *_: None)
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_controller_activation",
        lambda **_: "sha256:" + "b" * 64,
    )
    monkeypatch.setattr(
        "tcfactory.v3.activation.validate_activation_control_state", lambda **_: None
    )
    monkeypatch.setattr(
        "tcfactory.supervisor.validate_repository_release_controls",
        lambda **_: {"status": "PASS"},
    )
    monkeypatch.setattr(
        "tcfactory.supervisor.reconcile_publications",
        lambda **_: calls.append("reconcile") or [],
    )

    def reject_marker(*_: object) -> None:
        calls.append("marker")
        raise RuntimeError("exact-SHA marker intentionally unavailable")

    monkeypatch.setattr("tcfactory.supervisor._verify_migration_marker", reject_marker)
    write_json(tmp_path / "MIGRATION_COMPLETE_V3.json", {})
    with pytest.raises(RuntimeError, match="exact-SHA marker intentionally unavailable"):
        run_startup_preflight(repo_root)
    assert calls == ["reconcile", "marker"]


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
