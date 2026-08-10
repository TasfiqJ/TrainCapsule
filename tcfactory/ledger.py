from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import StageResult
from .util import read_json, write_json


class Ledger:
    def __init__(self, path: Path, monthly_budget_usd: float) -> None:
        self.path = path
        env_budget = os.getenv("TCF_MONTHLY_ESTIMATED_USD_CAP") or os.getenv(
            "TCF_MONTHLY_BUDGET_USD"
        )
        self.monthly_budget_usd = float(env_budget) if env_budget else monthly_budget_usd

    def _load(self) -> dict[str, Any]:
        return read_json(self.path, {"version": 1, "runs": []})

    def append(self, result: StageResult) -> None:
        data = self._load()
        data["runs"].append(result.model_dump(mode="json"))
        write_json(self.path, data)

    def current_month_cost(self) -> float:
        prefix = datetime.now(UTC).strftime("%Y%m")
        total = 0.0
        for run in self._load().get("runs", []):
            run_id = str(run.get("run_id", ""))
            if run_id.startswith(prefix):
                total += float(run.get("total_cost_usd", 0.0) or 0.0)
        return total

    def task_cost(self, task_id: str, run_id: str) -> float:
        return sum(
            float(run.get("total_cost_usd", 0.0) or 0.0)
            for run in self._load().get("runs", [])
            if run.get("task_id") == task_id and run.get("run_id") == run_id
        )

    def assert_budget(self, additional_budget: float = 0.0) -> None:
        current = self.current_month_cost()
        if current + additional_budget > self.monthly_budget_usd:
            raise RuntimeError(
                "Monthly API-equivalent usage-estimate cap would be exceeded: "
                f"${current:.2f} estimated, ${additional_budget:.2f} requested, "
                f"${self.monthly_budget_usd:.2f} cap. This is a local circuit breaker, "
                "not an Anthropic charge or an authoritative Max-plan quota reading."
            )
