"""Regression tests for the blocker evidence handed to autonomous self-repair.

Durable evidence for the defect: ``factory/feature_ledger.yaml`` recorded 20 identical
"Automatic re-specification ceiling reached." notes for T001 and the controller produced 21
``block t001`` commits, yet the reason passed to self-repair was built from ``notes[-1]``.
Because the ceiling note is de-duplicated before it is appended, ``notes[-1]`` stayed on an
older, unrelated note ("Infrastructure-only failure recovered without consuming a
specification revision."), which contradicts the actual durable failure record
``factory/queue/failed/T001.error.txt``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.autopilot import (
    RespecOutcome,
    _verified_repair_intent,  # pyright: ignore[reportPrivateUsage]
    is_factory_repair_required,
    recover_task_after_verified_repair,
    respec_block_reason,
    respec_failed_item,
    terminal_blocker_reason,
)
from tcfactory.checkpoints import CheckpointStore, new_checkpoint
from tcfactory.config import load_factory_config
from tcfactory.feature_ledger import FeatureItem, FeatureLedger, save_feature_ledger
from tcfactory.models import AutonomyConfig, AutonomyState, PipelineState
from tcfactory.pipeline import FACTORY_REPAIR_SCOPE_MARKER
from tcfactory.queue import queue_dirs

CEILING_NOTE = "Automatic re-specification ceiling reached."
STALE_NOTE = "Infrastructure-only failure recovered without consuming a specification revision."
DURABLE_ERROR = (
    "PipelineFailure: Mutating stage research failed after 3 bounded failures. "
    "Re-specification is required."
)


def _repo(tmp_path: Path) -> Path:
    source_root = Path(__file__).resolve().parents[1]
    (tmp_path / "config").mkdir()
    (tmp_path / "config/factory.yaml").write_text(
        (source_root / "config/factory.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _item(**overrides: object) -> FeatureItem:
    fields: dict[str, object] = {
        "task_id": "T001",
        "outcome": "Commit final source-of-truth bundle and precedence rules",
        "lead_role": "Spec",
        "phase": "P0",
        "status": "respec_required",
        "packet_path": "tasks/T001.yaml",
        "revisions": 3,
        "notes": [CEILING_NOTE, STALE_NOTE],
    }
    fields.update(overrides)
    return FeatureItem(**fields)  # type: ignore[arg-type]


def _ledger(item: FeatureItem) -> FeatureLedger:
    return FeatureLedger(source_of_truth="test", tasks=[item])


def _run_respec(
    repo: Path,
    item: FeatureItem,
    error_text: str,
    autonomy: AutonomyConfig | None = None,
) -> RespecOutcome:
    config = load_factory_config(repo / "config/factory.yaml")
    dirs = queue_dirs(repo, config)
    (dirs["failed"] / "T001.error.txt").write_text(error_text, encoding="utf-8")
    return asyncio.run(
        respec_failed_item(
            repo_root=repo,
            factory=config,
            autonomy=autonomy or AutonomyConfig(),
            ledger=_ledger(item),
            item=item,
        )
    )


def test_ceiling_block_reports_current_cause_and_durable_artifact(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    item = _item()

    outcome = _run_respec(repo, item, DURABLE_ERROR)

    assert outcome.changed is False
    assert outcome.block_reason == CEILING_NOTE
    assert outcome.evidence_path == "factory/queue/failed/T001.error.txt"
    assert item.status == "blocked"
    assert item.terminal_blocked is True
    # The de-duplicated ceiling note must not be appended a second time.
    assert item.notes.count(CEILING_NOTE) == 1


def test_repair_reason_never_reuses_a_stale_trailing_note(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    item = _item()

    outcome = _run_respec(repo, item, DURABLE_ERROR)
    reason = respec_block_reason(item, outcome)

    assert item.notes[-1] == STALE_NOTE, "fixture must reproduce the stale trailing note"
    assert STALE_NOTE not in reason
    assert CEILING_NOTE in reason
    assert "factory/queue/failed/T001.error.txt" in reason
    assert "exhausted automatic re-specification" in reason
    assert "revisions 3" in reason


def test_value_redesign_ceiling_reports_its_own_cause(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    item = _item(revisions=0, value_revisions=AutonomyConfig().value_redesign_limit, notes=[])

    outcome = _run_respec(
        repo, item, "PipelineFailure: material-value gate rejected the predeclared threshold."
    )
    reason = respec_block_reason(item, outcome)

    assert outcome.changed is False
    assert outcome.block_reason is not None
    assert "Material-value redesign ceiling reached" in outcome.block_reason
    assert "Material-value redesign ceiling reached" in reason
    assert outcome.evidence_path == "factory/queue/failed/T001.error.txt"


def test_controller_scope_gap_routes_to_factory_repair_without_new_revision(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    item = _item(revisions=9, notes=[])
    error = (
        f"PipelineFailure: {FACTORY_REPAIR_SCOPE_MARKER}: Reviewer adversary identified "
        "protected controller-owned repair targets: scripts/gates, "
        "tcfactory/research_policy.py."
    )

    outcome = _run_respec(repo, item, error)

    assert is_factory_repair_required(error)
    assert outcome.changed is False
    assert outcome.block_reason is not None
    assert "factory self-repair" in outcome.block_reason
    assert outcome.evidence_path == "factory/queue/failed/T001.error.txt"
    assert item.status == "blocked"
    assert item.terminal_blocked is True
    assert item.revisions == 9


def test_zero_respec_and_value_limits_mean_work_until_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    item = _item(revisions=100, value_revisions=100, notes=[])
    autonomy = AutonomyConfig(max_respecifications_per_task=0, value_redesign_limit=0)
    monkeypatch.setattr("tcfactory.autopilot.commit_all", _noop_commit_all)
    monkeypatch.setattr("tcfactory.autopilot.save_feature_ledger", _noop_save_feature_ledger)
    monkeypatch.setattr(
        "tcfactory.autopilot.create_and_promote_task_packet",
        _stub_create_and_promote_task_packet,
    )

    outcome = _run_respec(
        repo,
        item,
        "PipelineFailure: material-value gate rejected the predeclared threshold.",
        autonomy,
    )

    assert outcome.changed is True
    assert outcome.block_reason is None
    assert item.status == "ready"
    assert item.terminal_blocked is False
    assert item.revisions == 101
    assert item.value_revisions == 101
    assert any("Value redesign 101/unlimited" in note for note in item.notes)


def _noop_commit_all(*args: object, **kwargs: object) -> None:
    return None


def _noop_save_feature_ledger(*args: object, **kwargs: object) -> None:
    return None


def _fixed_recovery_commit(*args: object, **kwargs: object) -> str:
    return "new-main"


def _fixed_candidate_transplant(*args: object, **kwargs: object) -> str:
    return "rebased-candidate"


async def _stub_create_and_promote_task_packet(**kwargs: object) -> None:
    """Stand in for packet regeneration, which shells out to Git and Claude. Only the observable
    effect this test depends on is reproduced: the item points at an on-disk packet again."""
    item = kwargs["item"]
    item.packet_path = "tasks/T001.yaml"  # type: ignore[union-attr]


def test_infrastructure_failure_still_recovers_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    (repo / "tasks").mkdir()
    source_root = Path(__file__).resolve().parents[1]
    (repo / "tasks/T001.yaml").write_text(
        (source_root / "tasks/DEMO-001.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    item = _item(packet_path="tasks/T001.yaml", notes=[])
    monkeypatch.setattr("tcfactory.autopilot.commit_all", _noop_commit_all)
    monkeypatch.setattr("tcfactory.autopilot.save_feature_ledger", _noop_save_feature_ledger)

    outcome = _run_respec(
        repo, item, "ClaudeRunError: reached maximum number of turns during the research stage."
    )

    assert outcome.changed is True
    assert outcome.block_reason is None
    assert item.status == "queued"
    assert item.terminal_blocked is False


def test_repeated_infrastructure_recovery_at_ceiling_eventually_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reproduces the durable failure: infrastructure recovery does not consume a revision,
    so a task already at the re-specification ceiling could be requeued and immediately
    re-blocked forever, burning an unbounded number of self-repair cycles on T001. Recovery
    must still work while budget remains, but must not be able to loop without limit once the
    ceiling is exhausted.
    """
    repo = _repo(tmp_path)
    (repo / "tasks").mkdir()
    source_root = Path(__file__).resolve().parents[1]
    (repo / "tasks/T001.yaml").write_text(
        (source_root / "tasks/DEMO-001.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    item = _item(packet_path="tasks/T001.yaml", notes=[])
    monkeypatch.setattr("tcfactory.autopilot.commit_all", _noop_commit_all)
    monkeypatch.setattr("tcfactory.autopilot.save_feature_ledger", _noop_save_feature_ledger)
    infra_error = "ClaudeRunError: reached maximum number of turns during the research stage."
    limit = AutonomyConfig().max_consecutive_infrastructure_recoveries

    outcomes = [_run_respec(repo, item, infra_error) for _ in range(limit)]
    for outcome in outcomes:
        assert outcome.changed is True
        assert item.status == "queued"
        assert item.terminal_blocked is False
    assert item.revisions == 3, "infrastructure recovery must never consume a revision"

    final_outcome = _run_respec(repo, item, infra_error)

    assert final_outcome.changed is False
    assert item.status == "blocked"
    assert item.terminal_blocked is True
    assert final_outcome.block_reason is not None
    assert "operator intervention" in final_outcome.block_reason
    assert item.revisions == 3, "the terminal block must still not fabricate a spec revision"


def test_infrastructure_recovery_below_the_ceiling_is_also_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counterexample for the first repair attempt: the recovery counter was only incremented
    once the re-specification ceiling was already exhausted, so a task starting at revisions=0
    never incremented it, never reached the ceiling, and could be requeued forever on
    infrastructure-classified failures (for example an under-sized ``max_turns``). Every
    infrastructure recovery must consume recovery budget, and exhausting that budget below the
    ceiling must escalate to a bounded re-specification instead of looping.
    """
    repo = _repo(tmp_path)
    (repo / "tasks").mkdir()
    source_root = Path(__file__).resolve().parents[1]
    (repo / "tasks/T001.yaml").write_text(
        (source_root / "tasks/DEMO-001.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    item = _item(packet_path="tasks/T001.yaml", revisions=0, notes=[])
    monkeypatch.setattr("tcfactory.autopilot.commit_all", _noop_commit_all)
    monkeypatch.setattr("tcfactory.autopilot.save_feature_ledger", _noop_save_feature_ledger)
    monkeypatch.setattr(
        "tcfactory.autopilot.create_and_promote_task_packet",
        _stub_create_and_promote_task_packet,
    )
    infra_error = "ClaudeRunError: reached maximum number of turns during the research stage."
    autonomy = AutonomyConfig()
    limit = autonomy.max_consecutive_infrastructure_recoveries
    ceiling = autonomy.max_respecifications_per_task

    # Recovery budget is consumed even at revisions=0.
    for _ in range(limit):
        outcome = _run_respec(repo, item, infra_error)
        assert outcome.changed is True
        assert item.status == "queued"
    assert item.infrastructure_recoveries == limit
    assert item.revisions == 0, "recovery must not consume a revision while budget remains"

    # Exhausting the budget below the ceiling escalates to a re-specification, not another loop.
    escalation = _run_respec(repo, item, infra_error)
    assert escalation.changed is True
    assert escalation.block_reason is None
    assert item.status == "ready"
    assert item.revisions == 1
    assert item.infrastructure_recoveries == 0
    assert any("consumes a revision" in note for note in item.notes)

    # The whole loop terminates: it can never exceed (ceiling + 1) * (limit + 1) calls.
    max_calls = (ceiling + 1) * (limit + 1)
    calls = limit + 1
    final: RespecOutcome | None = None
    while calls < max_calls + 5:
        final = _run_respec(repo, item, infra_error)
        calls += 1
        if not final.changed:
            break
    assert final is not None
    assert final.changed is False, "unbounded infrastructure recovery: the loop never terminated"
    assert calls <= max_calls
    assert item.status == "blocked"
    assert item.terminal_blocked is True
    assert final.block_reason is not None
    assert "operator intervention" in final.block_reason
    assert item.revisions == ceiling


def test_missing_error_artifact_is_reported_truthfully(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    config = load_factory_config(repo / "config/factory.yaml")
    queue_dirs(repo, config)
    item = _item()

    outcome = asyncio.run(
        respec_failed_item(
            repo_root=repo,
            factory=config,
            autonomy=AutonomyConfig(),
            ledger=_ledger(item),
            item=item,
        )
    )
    reason = respec_block_reason(item, outcome)

    assert outcome.changed is False
    assert outcome.evidence_path is None
    assert "no queue error artifact recorded" in reason


def test_verified_repair_reopens_root_task_and_preserves_candidate_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    source_root = Path(__file__).resolve().parents[1]
    (repo / "tasks").mkdir()
    (repo / "tasks/T001.yaml").write_text(
        (source_root / "tasks/T001.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    item = _item(status="blocked", terminal_blocked=True, infrastructure_recoveries=2)
    ledger = _ledger(item)
    (repo / "factory").mkdir(exist_ok=True)
    save_feature_ledger(repo / "factory/feature_ledger.yaml", ledger)
    config = load_factory_config(repo / "config/factory.yaml")
    store = CheckpointStore(config.resolve(repo, config.pipeline_state_dir))
    checkpoint = new_checkpoint(task_id="T001", run_id="old-run", starting_sha="old-main")
    checkpoint.candidate_sha = "old-candidate"
    checkpoint.state = PipelineState.FAILED
    checkpoint.previous_findings = ["preserve this finding"]
    store.save(checkpoint)
    failed = queue_dirs(repo, config)["failed"] / "T001.yaml"
    failed.write_text((repo / "tasks/T001.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    failed.with_suffix(".error.txt").write_text("controller defect\n", encoding="utf-8")
    state = AutonomyState(
        status="stopped",
        updated_at=datetime.now(UTC),
    )
    repair_result = repo / "factory/state/self-repair/FACTORY_REPAIR_20260810T000000Z_1.result.json"
    repair_result.parent.mkdir(parents=True)
    repair_result.write_text('{"applied": true}\n', encoding="utf-8")
    monkeypatch.setattr("tcfactory.autopilot.commit_all", _fixed_recovery_commit)
    monkeypatch.setattr(
        "tcfactory.autopilot.transplant_candidate_onto", _fixed_candidate_transplant
    )

    assert recover_task_after_verified_repair(
        repo_root=repo,
        factory=config,
        state=state,
        ledger=ledger,
    )

    recovered = store.load("T001")
    assert recovered is not None
    assert recovered.starting_sha == "new-main"
    assert recovered.candidate_sha == "rebased-candidate"
    assert recovered.state == PipelineState.RUNNING
    assert recovered.previous_findings is not None
    assert "preserve this finding" in recovered.previous_findings
    assert list((store.root / "archive").glob("T001-controller-repair-*.json"))
    assert (queue_dirs(repo, config)["pending"] / "T001.yaml").is_file()
    assert not failed.exists()
    assert item.status == "queued"
    assert item.terminal_blocked is False
    assert item.infrastructure_recoveries == 0
    assert state.status == "running"
    assert state.repair_status is None
    assert state.active_task_id == "T001"
    consumed = repo / "factory/state/VERIFIED_REPAIR_RETRY_CONSUMED.json"
    assert str(repair_result) in consumed.read_text(encoding="utf-8")


def test_consumed_marker_does_not_replay_an_older_migration_artifact(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    item = _item(status="queued", terminal_blocked=False)
    ledger = _ledger(item)
    state = AutonomyState(
        status="running",
        active_task_id="T001",
        updated_at=datetime.now(UTC),
    )
    old_result = (
        repo
        / "factory/state/self-repair/FACTORY_REPAIR_20260810T000000Z_1.result.json"
    )
    old_result.parent.mkdir(parents=True)
    old_result.write_text('{"applied": true}\n', encoding="utf-8")
    consumed_at = datetime.now(UTC)
    consumed = repo / "factory/state/VERIFIED_REPAIR_RETRY_CONSUMED.json"
    consumed.write_text(
        (
            '{"artifact_path": "git:new-repair", '
            f'"recovered_at": "{consumed_at.isoformat()}", '
            '"repair_status_consumed": true, "task_id": "T001"}\n'
        ),
        encoding="utf-8",
    )

    recovered_item, artifact = _verified_repair_intent(repo, state, ledger)

    assert recovered_item is None
    assert artifact is None


def test_terminal_blocker_reason_uses_current_queue_error_not_stale_note(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    config = load_factory_config(repo / "config/factory.yaml")
    item = _item(status="blocked", terminal_blocked=True)
    error = queue_dirs(repo, config)["failed"] / "T001.error.txt"
    error.write_text(DURABLE_ERROR + "\n", encoding="utf-8")

    reason = terminal_blocker_reason(repo, config, item)

    assert DURABLE_ERROR in reason
    assert "factory/queue/failed/T001.error.txt" in reason
    assert STALE_NOTE not in reason
