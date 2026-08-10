from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from .util import read_json


def _numeric_total(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        return sum(_numeric_total(item) for item in cast(dict[object, object], value).values())
    if isinstance(value, list):
        return sum(_numeric_total(item) for item in cast(list[object], value))
    return 0


def _family(model: object) -> str:
    value = str(model or "unknown").lower()
    if "fable" in value:
        return "fable"
    if "opus" in value:
        return "opus"
    if "sonnet" in value:
        return "sonnet"
    if "haiku" in value:
        return "haiku"
    return "other"


def usage_health(path: Path) -> dict[str, Any]:
    ledger = cast(dict[str, object], read_json(path, {"runs": []}))
    runs = cast(list[object], ledger.get("runs", []))
    by_family: dict[str, dict[str, float]] = defaultdict(
        lambda: {"stages": 0.0, "estimated_usd": 0.0, "reported_usage": 0.0}
    )
    for raw_run in runs:
        if not isinstance(raw_run, dict):
            continue
        run = cast(dict[str, object], raw_run)
        family = _family(run.get("model"))
        by_family[family]["stages"] += 1
        raw_cost = run.get("total_cost_usd", 0.0)
        cost = float(raw_cost) if isinstance(raw_cost, (int, float)) else 0.0
        by_family[family]["estimated_usd"] += cost
        usage: object = run.get("usage") or run.get("model_usage") or {}
        by_family[family]["reported_usage"] += _numeric_total(usage)

    total_usage = sum(value["reported_usage"] for value in by_family.values())
    total_cost = sum(value["estimated_usd"] for value in by_family.values())
    denominator = total_usage or total_cost or sum(value["stages"] for value in by_family.values())

    def share(family: str) -> float:
        value = (
            by_family[family]["reported_usage"]
            if total_usage
            else by_family[family]["estimated_usd"]
            if total_cost
            else by_family[family]["stages"]
        )
        return value / denominator if denominator else 0.0

    shares = {
        family: share(family)
        for family in ("haiku", "sonnet", "opus", "fable", "other")
    }
    status = "healthy"
    if runs and shares["fable"] > 0.25:
        status = "fable-heavy"
    elif runs and shares["opus"] + shares["fable"] > 0.45:
        status = "premium-model-heavy"
    elif runs and shares["opus"] > 0.35:
        status = "opus-heavy"
    elif runs and shares["sonnet"] < 0.55:
        status = "sonnet-underused"
    elif shares["other"] > 0:
        status = "unexpected-model"

    return {
        "status": status,
        "shares": shares,
        "target": (
            "Sonnet should perform most production work; Haiku only mechanical work; "
            "Opus should remain concentrated on integration/trust/security stages; "
            "Fable should remain below 25% and appear only on trust-core implementation."
        ),
        "by_family": dict(by_family),
        "stage_count": len(runs),
    }
