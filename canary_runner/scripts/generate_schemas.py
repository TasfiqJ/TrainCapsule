#!/usr/bin/env python3
"""Generate the public wire schemas for the isolated canary distribution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel
from traincapsule_canary_runner.models import (
    MandatoryCanaryResult,
    MechanismOutcome,
    MechanismPolicy,
    RunnerPolicy,
)

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "mandatory-canary-result.schema.json": MandatoryCanaryResult,
    "mechanism-outcome.schema.json": MechanismOutcome,
    "mechanism-policy.schema.json": MechanismPolicy,
    "runner-policy.schema.json": RunnerPolicy,
}


def _render(model: type[BaseModel]) -> bytes:
    schema = model.model_json_schema(by_alias=True)
    return (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "schemas"
    expected = {name: _render(model) for name, model in MODELS.items()}
    if args.check:
        observed = {path.name for path in destination.glob("*.schema.json")}
        if observed != set(expected):
            raise SystemExit("canary schema roster is stale")
        for name, content in expected.items():
            if (destination / name).read_bytes() != content:
                raise SystemExit(f"canary schema is stale: {name}")
        print(f"PASS: exact {len(expected)} canary runner schemas")
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (destination / name).write_bytes(content)
    print(f"Wrote {len(expected)} canary runner schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
