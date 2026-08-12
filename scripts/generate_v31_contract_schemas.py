#!/usr/bin/env python3
"""Generate and verify checked-in TrainCapsule V3.1-ZH contract schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from pydantic import BaseModel

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.base import json_schema_for  # noqa: E402
from tcfactory.v3.contracts_v31 import (  # noqa: E402
    REUSABLE_V3_MIGRATIONS,
    V31_NATIVE_CONTRACTS,
)
from tcfactory.v3.native_value_gate import NATIVE_VALUE_CONTRACTS  # noqa: E402
from tcfactory.v3.source_acquisition import SOURCE_ACQUISITION_CONTRACTS  # noqa: E402

SCHEMA_ROOT: Final = ROOT / "schemas/factory/v3.1"
SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    **{f"{name}.schema.json": model for name, model in V31_NATIVE_CONTRACTS.items()},
    **{f"migrated-{name}.schema.json": model for name, model in REUSABLE_V3_MIGRATIONS.items()},
    **{f"{name}.schema.json": model for name, model in SOURCE_ACQUISITION_CONTRACTS.items()},
    **{f"{name}.schema.json": model for name, model in NATIVE_VALUE_CONTRACTS.items()},
}


def rendered_schemas() -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, model in sorted(SCHEMAS.items()):
        schema = json_schema_for(model)
        schema["$id"] = f"https://traincapsule.local/schemas/factory/v3.1/{name}"
        rendered[name] = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = rendered_schemas()
    if args.check:
        stale = [
            name
            for name, content in expected.items()
            if not (SCHEMA_ROOT / name).is_file()
            or (SCHEMA_ROOT / name).read_bytes() != content.encode("utf-8")
        ]
        unexpected = sorted(
            path.name for path in SCHEMA_ROOT.glob("*.schema.json") if path.name not in expected
        )
        if stale or unexpected:
            raise SystemExit(
                f"V3.1 schemas are stale: missing/changed={stale}, unexpected={unexpected}"
            )
        print(f"PASS: {len(expected)} V3.1 schemas match their Pydantic models")
        return 0
    SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (SCHEMA_ROOT / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {len(expected)} V3.1 schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
