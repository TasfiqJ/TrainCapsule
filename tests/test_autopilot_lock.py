from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.autopilot import AutopilotError, exclusive_autopilot_lock
from tcfactory.models import FactoryConfig


def test_autopilot_lock_rejects_duplicate_controller(tmp_path: Path) -> None:
    config = FactoryConfig(autopilot_lock_path="state/autopilot.lock")
    with (
        exclusive_autopilot_lock(tmp_path, config),
        pytest.raises(AutopilotError, match="Another TrainCapsule autopilot"),
        exclusive_autopilot_lock(tmp_path, config),
    ):
        raise AssertionError("unreachable")
