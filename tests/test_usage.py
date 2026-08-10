from __future__ import annotations

import json
from pathlib import Path

from tcfactory.usage import usage_health


def test_usage_health_reports_fable_separately(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "runs": [
                    {"model": "fable", "usage": {"input_tokens": 30}},
                    {"model": "sonnet", "usage": {"input_tokens": 70}},
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = usage_health(ledger)

    assert summary["shares"]["fable"] == 0.3
    assert summary["shares"]["sonnet"] == 0.7
    assert summary["status"] == "fable-heavy"
