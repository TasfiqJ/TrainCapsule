from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import tcfactory.v3.milestone_runtime as milestone_runtime
from tcfactory.v3.milestone_runtime import (
    advance_milestone_state,
    initialize_milestone_state,
)
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_milestone_advance_transaction_replays_after_state_write_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    state_path = tmp_path / "milestone-state.json"
    receipt_path = tmp_path / "milestone-decisions/M1_NATIVE_PREFLIGHT.json"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    initial = initialize_milestone_state(roadmap, state_path, now=now)
    assert initial.active_milestone == "M1_NATIVE_PREFLIGHT"
    original_write_json = milestone_runtime.write_json
    failed = False

    def crash_before_state(path: Path, payload: object) -> None:
        nonlocal failed
        transaction = state_path.with_name(f".{state_path.name}.advance-transaction.json")
        if path == state_path and transaction.is_file() and not failed:
            failed = True
            raise OSError("simulated crash before milestone state commit")
        original_write_json(path, payload)

    monkeypatch.setattr(milestone_runtime, "write_json", crash_before_state)
    with pytest.raises(OSError, match="simulated crash"):
        advance_milestone_state(
            roadmap=roadmap,
            state_path=state_path,
            receipt_path=receipt_path,
            evidence_digests={"V3-SIM-001": "sha256:" + "a" * 64},
            owner_directives_digest="sha256:" + "b" * 64,
            now=now,
        )
    monkeypatch.setattr(milestone_runtime, "write_json", original_write_json)

    recovered = initialize_milestone_state(roadmap, state_path, now=now)
    assert recovered.active_milestone == "M2_CONTROLLED_QUALIFICATION"
    assert receipt_path.is_file()
    assert not state_path.with_name(
        f".{state_path.name}.advance-transaction.json"
    ).exists()
